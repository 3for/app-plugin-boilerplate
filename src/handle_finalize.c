#include "plugin.h"

void handle_finalize(ethPluginFinalize_t *msg) {
    context_t *context = (context_t *) msg->pluginContext;
    if (msg->txContent != NULL) {
        PRINTF("finalize contractAddress(TRON): %.*H\n",
               TRON_ADDRESS_SIZE,
               msg->txContent->contractAddress);
    }
    PRINTF("finalize to_address(EVM): %.*H\n", ADDRESS_LENGTH, context->to_address);

    msg->uiType = ETH_UI_TYPE_GENERIC;

    // EDIT THIS: Set the total number of screen you will need.
    msg->numScreens = 2;
    // EDIT THIS: Handle this case like you wish to (i.e. maybe no additional screen needed?).
    // If the to_address is NOT the contract, we will need an additional screen to display it.
    // TRON contractAddress is 21 bytes (0x41 + 20-byte EVM payload). Compare only the 20-byte
    // payload with the parsed EVM `to_address`.
    if (msg->txContent == NULL ||
        memcmp(msg->txContent->contractAddress + 1, context->to_address, ADDRESS_LENGTH) != 0) {
        msg->numScreens += 1;
    }

    // EDIT THIS: set `tokenLookup1` (and maybe `tokenLookup2`) to point to
    // token addresses you will info for (such as decimals, ticker...).
    msg->tokenLookup1 = NULL; // TODO. Not proper here.

    msg->result = ETH_PLUGIN_RESULT_OK;
}
