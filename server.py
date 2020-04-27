#   -*- coding: utf-8 -*-
#
#   This file is part of SKALE Transaction Manager
#
#   Copyright (C) 2019 SKALE Labs
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

import json
import logging
import threading
from http import HTTPStatus

from flask import Flask, request
from skale import Skale
from skale.utils.helper import init_default_logger
from skale.utils.web3_utils import init_web3

from nonce_manager import NonceManager

from core import wait_for_the_next_block
from tools.str_formatters import arguments_list_string
from tools.helper import construct_ok_response, construct_err_response, init_wallet

from configs.flask import FLASK_APP_HOST, FLASK_APP_PORT, FLASK_DEBUG_MODE, FLASK_SECRET_KEY
from configs.web3 import ENDPOINT, ABI_FILEPATH

init_default_logger()

threadLock = threading.Lock()
logger = logging.getLogger(__name__)
app = Flask(__name__)

web3 = init_web3(ENDPOINT)
wallet = init_wallet(web3)
skale = Skale(ENDPOINT, ABI_FILEPATH, wallet)
nonce_manager = NonceManager(skale, wallet)


@app.route('/sign-and-send', methods=['POST'])
def _sign_and_send():
    logger.debug(request)
    transaction_dict_str = request.json.get('transaction_dict')
    transaction_dict = json.loads(transaction_dict_str)
    with threadLock:
        transaction_dict['nonce'] = nonce_manager.nonce
        try:
            tx = wallet.sign_and_send(transaction_dict)
        except Exception as e:  # todo: catch specific error
            logger.error(e)
            return construct_err_response(HTTPStatus.BAD_REQUEST, e)
        nonce_manager.increment()
        logger.info(f'Transaction sent - tx: {tx}, nonce: {transaction_dict["nonce"]}')
        return construct_ok_response({'transaction_hash': tx})


@app.route('/sign', methods=['POST'])
def _sign():
    logger.debug(request)
    transaction_dict_str = request.json.get('transaction_dict')
    transaction_dict = json.loads(transaction_dict_str)
    try:
        signed_transaction = wallet.sign(transaction_dict)
    except Exception as e:  # todo: catch specific error
        logger.error(e)
        return construct_err_response(HTTPStatus.BAD_REQUEST, e)
    logger.info(f'Transaction signed - {signed_transaction}')
    return construct_ok_response({
        'rawTransaction': signed_transaction.rawTransaction.hex(),
        'hash': signed_transaction.hash.hex(),
        'r': signed_transaction.r,
        's': signed_transaction.s,
        'v': signed_transaction.v
    })


@app.route('/sign-hash', methods=['POST'])
def _sign_hash():
    logger.debug(request)
    unsigned_hash = request.json.get('unsigned_hash')
    try:
        signed_data = wallet.sign_hash(unsigned_hash)
    except Exception as e:  # todo: catch specific error
        logger.error(e)
        return construct_err_response(HTTPStatus.BAD_REQUEST, e)
    logger.info(f'Hash signed - signed hash: {signed_data}')

    # from eth_account._utils import signing
    # v, r, s = signed_data.v, signed_data.r, signed_data.s
    # signature_bytes = signing.to_bytes(v) + signing.to_bytes32(r) + signing.to_bytes32(s)

    data = {
        'messageHash': signed_data.messageHash.hex(),
        'r': signed_data.r,
        's': signed_data.s,
        'v': signed_data.v,
        'signature': signed_data.signature.hex()
    }
    return construct_ok_response(data)


@app.route('/address', methods=['GET'])
def _address():
    logger.debug(request)
    return construct_ok_response({'address': wallet.address})


@app.route('/public-key', methods=['GET'])
def _public_key():
    logger.debug(request)
    return construct_ok_response({'public_key': wallet.public_key})


if __name__ == '__main__':
    logger.info(arguments_list_string({
        'Ethereum RPC endpoint': ENDPOINT}, 'Starting Transaction Manager'))
    app.secret_key = FLASK_SECRET_KEY

    wait_for_the_next_block(skale)
    nonce_manager.request_network_nonce()
    app.run(debug=FLASK_DEBUG_MODE, port=FLASK_APP_PORT, host=FLASK_APP_HOST, use_reloader=False)
