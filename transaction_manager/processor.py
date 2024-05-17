#   -*- coding: utf-8 -*-
#
#   This file is part of SKALE Transaction Manager
#
#   Copyright (C) 2021 SKALE Labs
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional, Tuple

from skale.wallets import BaseWallet  # type: ignore

from .attempt_manager import BaseAttemptManager
from .config import CONFIRMATION_BLOCKS, UNDERPRICED_RETRIES
from .eth import (
    EstimateGasRevertError,
    Eth,
    is_replacement_underpriced,
    ReceiptTimeoutError
)
from .resources import stdc
from .structures import Tx, TxStatus
from .txpool import TxPool

logger = logging.getLogger(__name__)


class ConfirmationError(Exception):
    pass


class SendingError(Exception):
    pass


class WaitTimeoutError(Exception):
    pass


class Processor:
    def __init__(
        self,
        eth: Eth,
        pool: TxPool,
        attempt_manager: BaseAttemptManager,
        wallet: BaseWallet
    ) -> None:
        self.eth: Eth = eth
        self.attempt_manager = attempt_manager
        self.pool: TxPool = pool
        self.wallet: BaseWallet = wallet
        self.address = wallet.address

    def send(self, tx: Tx) -> None:
        tx_hash, err = None, None
        retry = 0
        replaced = False
        while tx_hash is None and retry < UNDERPRICED_RETRIES:
            logger.info('Signing tx %s, retry %d', tx.tx_id, retry)
            etx = self.eth.convert_tx(tx)
            signed = self.wallet.sign(etx)
            logger.info('Sending transaction %s', tx)
            try:
                tx_hash = self.eth.send_tx(signed)
            except Exception as e:
                logger.info(f'Sending failed with error {err}')
                err = e
                if is_replacement_underpriced(err):
                    logger.info('Replacement fee is too low. Increasing')
                    self.attempt_manager.replace(tx, replace_attempt=retry)
                    replaced = True
                    retry += 1
                else:
                    break

        if tx_hash is not None or replaced:
            self.attempt_manager.save()

        if tx_hash is None:
            tx.status = TxStatus.UNSENT
            raise SendingError(err)

        tx.set_as_sent(tx_hash)
        self.pool.save(tx)
        logger.info(f'Tx {tx.tx_id} was sent successfully')

    def wait(self, tx: Tx, max_time: int) -> Optional[int]:
        if not tx.tx_hash:
            logger.warning(f'Tx {tx.tx_id} has not any receipt')
            return None
        try:
            logger.info(
                'Waiting for %s, with hash %s, timeout %d',
                tx.tx_id, tx.tx_hash, max_time
            )
            self.eth.wait_for_receipt(
                tx_hash=tx.tx_hash,
                max_time=max_time
            )
        except ReceiptTimeoutError as err:
            logger.info(f'{tx.tx_id} is not mined within {max_time}')
            tx.status = TxStatus.TIMEOUT
            raise WaitTimeoutError(err)

        rstatus = self.eth.wait_for_receipt(
            tx_hash=tx.tx_hash,
            max_time=max_time
        )
        if rstatus is not None:
            logger.info('Setting tx %s as mined', tx.tx_id)
            tx.set_as_mined()
            self.pool.save(tx)
        return rstatus

    def confirm(self, tx: Tx) -> None:
        logger.info(
            'Tx %s: confirming within %d blocks',
            tx.tx_id, CONFIRMATION_BLOCKS
        )
        start_block = self.eth.get_tx_block(tx.tx_hash)  # type: ignore
        self.eth.wait_for_blocks(
            amount=CONFIRMATION_BLOCKS,
            start_block=start_block
        )
        h, r = self.get_exec_data(tx)
        if h is None or r not in (0, 1):
            tx.status = TxStatus.UNCONFIRMED
            raise ConfirmationError('Tx is not confirmed')
        logger.info('Setting tx %s as completed, result %d', tx.tx_id, r)
        tx.set_as_completed(h, r)
        self.pool.save(tx)
        logger.info('Tx %s was confirmed', tx.tx_id)

    def get_exec_data(self, tx: Tx) -> Tuple[Optional[str], Optional[int]]:
        for h in reversed(tx.hashes):
            r = self.eth.get_status(h)
            if r >= 0:
                return h, r
        return None, None

    def process(self, tx: Tx) -> None:
        tx.chain_id = self.eth.chain_id
        tx.source = self.wallet.address

        if tx.is_sent():
            _, rstatus = self.get_exec_data(tx)
            if rstatus is not None:
                logger.info('Tx %s has been already mined', tx.tx_id)
                self.confirm(tx)
                return

        try:
            self.attempt_manager.make(tx)
        except EstimateGasRevertError as e:
            logger.info('Estimate gas failed for %s with %s', tx.tx_id, e)
            if tx.is_sent_by_ima():
                logger.info('Dropping tx with failed dry run from IMA %s', tx.tx_id)
                tx.set_as_dropped()
            raise

        logger.info('Current attempt: %s', self.attempt_manager.current)

        self.send(tx)

        rstatus = self.wait(
            tx,
            self.attempt_manager.current.wait_time  # type: ignore
        )
        if rstatus is not None:
            self.confirm(tx)

    @contextmanager
    def acquire_tx(self, tx: Tx) -> Generator[Tx, None, None]:
        logger.info('Aquiring %s. Attempt %s', tx.tx_id, tx.attempts)
        tx.attempts += 1
        if tx.status == TxStatus.PROPOSED:
            tx.status = TxStatus.SEEN
        try:
            yield tx
        finally:
            stdc.gauge('tm.attempt', tx.attempts)
            stdc.incr(f'tm.transaction.{tx.status.name}')
            if tx.is_sent():
                self.attempt_manager.save()
            if not tx.is_completed() and tx.is_last_attempt():
                tx.set_as_dropped()
            if tx.is_completed():
                self.pool.release(tx)
            else:
                self.pool.save(tx)

    def process_next(self) -> None:
        txs = self.pool.to_list()
        if txs:
            logger.info('Pool: %s', txs)
        tx = self.pool.fetch_next()
        self.attempt_manager.fetch()
        if tx is not None:
            with self.acquire_tx(tx) as tx:
                logger.info(
                    'Previous attempt %s', self.attempt_manager.current)
                with stdc.timer('tm.transaction.time'):
                    self.process(tx)

    def run(self) -> None:
        while True:
            try:
                stdc.gauge('tm.pool.size', self.pool.size)
                self.process_next()
            except Exception:
                logger.exception('Failed to process tx')
                logger.info('Waiting for next tx')
            finally:
                time.sleep(1)
