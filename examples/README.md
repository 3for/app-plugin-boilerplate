# Examples

`swap_exact_eth_for_token.py` is the physical-device counterpart of `tests/test_swap.py::test_swap_exact_eth_for_token`.

It does three things:

1. Connects to a real Ledger device through `ragger`'s physical backend.
2. Sends the same `set_external_plugin` request used by the test.
3. Builds and signs the same `swapExactETHForTokens` transaction, then verifies the signature locally.

## Prerequisites

- The Ledger device is unlocked and connected over USB.
- The `Ethereum` app is installed on the device.
- This plugin is installed on the device as well.
- Use the repository Python environment, for example `ledger310/bin/python3`.

Important: this example uses the local signing material bundled with `ledger_app_clients.ethereum` to build the `external plugin` setup APDU, exactly like the functional test does. A production Ledger Ethereum app can reject that metadata if it expects Ledger CAL production signatures. In that case, the script will stop during `set_external_plugin`.

Important: in Ethereum app `1.20.x`, `GET_PUBLIC_KEY` resets the in-memory plugin context. The script therefore fetches the wallet address before `set_external_plugin`, and performs signing immediately after `set_external_plugin`.

## Run

Example command:

```bash
ledger310/bin/python3 examples/swap_exact_eth_for_token.py --device nanox
```

Useful options:

- `--backend ledgercomm|ledgerwallet`
- `--device nanos|nanosp|nanox|stax|flex|apex_p|apex_m`
- `--skip-open-app` if you want to open the `Ethereum` app manually
- `--with-gui` to show Ragger's helper window for physical interaction
- `--deadline <unix_timestamp>`
- `--value-eth`, `--amount-out-min-eth`, `--path`, `--recipient`

The script does not broadcast the transaction. It only asks the Ledger device to sign and then verifies that the recovered signer matches the device address.
