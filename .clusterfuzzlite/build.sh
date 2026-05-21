#!/bin/bash -eu

# build fuzzers

pushd fuzzing

# Regenerate seed corpus + dictionary so they always match the current source
# (selectors in plugin.h, txContent_t / extraInfo_t sizes from the SDK).
python3 seed_corpus_gen.py

cmake \
    -DBOLOS_SDK=../BOLOS_SDK \
    -DFUZZ_HEARTBEAT_INTERVAL="${FUZZ_HEARTBEAT_INTERVAL:-10000000}" \
    -Bbuild -H.
make -C build
mv ./build/fuzz "${OUT}"

# OSS-Fuzz convention: the runner auto-passes `-dict=$OUT/<fuzzer>.dict` when
# this file exists, and unpacks `$OUT/<fuzzer>_seed_corpus.zip` into the
# corpus directory at run time.
cp plugin.dict "${OUT}/fuzz.dict"
( cd corpus && zip -qr "${OUT}/fuzz_seed_corpus.zip" . )

popd
