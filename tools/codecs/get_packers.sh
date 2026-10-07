#!/bin/bash
# Run in WSL: fetches and builds the two packers build_release.sh uses, into ~/codecs
#   apultra  (aPLib packer, Emmanuel Marty)  - the game image
#   salvador (ZX0 packer, Emmanuel Marty)    - the loading screen
set -e
mkdir -p ~/codecs && cd ~/codecs
for n in apultra salvador; do
  [ -d $n ] || git clone -q --depth 1 https://github.com/emmanuel-marty/$n
  (cd $n && make -s)
done
ls -l apultra/apultra salvador/salvador
