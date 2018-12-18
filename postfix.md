## See progress
in [#sebak-monitor](https://bosplatform.slack.com/archives/CEGT607PH)


## Error kinds and examples
1. There is no valid url.
There is no response from these urls.
https://mainnet-node-0.blockchainos.org
https://mainnet-node-1.blockchainos.org
https://mainnet-node-2.blockchainos.org
https://mainnet-node-3.blockchainos.org

2. The latest_height has not changed for 20 seconds.
[KNOWN ISSUE] `SEBAK` is stuck.
We should restart the `SEBAK`.

3. At height 214241, the block hashes of the two nodes are different.
[CRITICAL] `SEBAK` blockchain has forked.
We should select one chain.

4. The latest_height(0) is invalid.
There is no 0 block height. Invalid.

