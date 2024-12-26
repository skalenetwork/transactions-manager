#!/usr/bin/env bash
set -ae

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_DIR=$(dirname $DIR)

cd $PROJECT_DIR

export REDIS_DIR=./tests/data-volumes/redis-dir

create_redis_dir() {
    mkdir -p $REDIS_DIR/redis-data
    mkdir -p $REDIS_DIR/redis-config
    cp tests/utils/redis.conf $REDIS_DIR/redis-config
}

run_container() {
    docker compose up --build --force-recreate -d redis
}

shutdown_container() {
    docker compose down --rmi local
}

cleanup_redis_dir() {
    if [ -d $REDIS_DIR ]; then
        rm -r --interactive=never $REDIS_DIR
    fi
}

shutdown_container
cleanup_redis_dir
create_redis_dir
run_container
