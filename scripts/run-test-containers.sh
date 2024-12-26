#!/usr/bin/env bash
set -ae

: "${ENDPOINT?Need to set ENDPOINT}"
: "${ETH_PRIVATE_KEY?Need to set ETH_PRIVATE_KEY}"


DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_DIR=$(dirname $DIR)

cd $PROJECT_DIR

export SKALE_DIR=./tests/data-volumes/skale-dir
export REDIS_DIR=./tests/data-volumes/redis-dir
export SGX_DIR=./tests/data-volumes/skale-dir/node_data/sgx-dir
export PYTHONPATH=${PYTHONPATH}:${PROJECT_DIR}

create_skale_dir() {
    mkdir -p $SKALE_DIR/node_data/log
}

create_redis_dir() {
    mkdir -p $REDIS_DIR/redis-data
    mkdir -p $REDIS_DIR/redis-config
    cp tests/utils/redis.conf $REDIS_DIR/redis-config
}

build() {
    docker compose build --force-rm $@
}

run_containers() {
    docker compose up -d $@
}

shutdown_containers() {
    docker compose down --rmi local
}

cleanup_skale_dir() {
    if [ -d $SKALE_DIR ]; then
        sudo rm -r --interactive=never $SKALE_DIR
    fi
}

cleanup_redis_dir() {
    if [ -d $REDIS_DIR ]; then
        sudo rm -r --interactive=never $REDIS_DIR
    fi
}

gen_sgx_key() {
    python3 tests/gen_sgx.py
}

deploy_test_contract() {
    cd tests/tester-contract/
    yarn install
    npx hardhat run --network localhost scripts/deploy.ts
    cd -
}

shutdown_containers
cleanup_skale_dir
cleanup_redis_dir
create_skale_dir
create_redis_dir
build tm

if [ -z ${SGX_URL} ]; then
    run_containers tm redis hnode
else
    run_containers sgx tm redis hnode
    gen_sgx_key
fi

deploy_test_contract
