#include "plugin.h"

void handle_finalize(tronPluginFinalize_t *msg) {
    context_t *context = (context_t *) msg->pluginContext;
    PRINTF("finalize selectorIndex: %d\n", context->selectorIndex);
    if (msg->txContent != NULL) {
        PRINTF("finalize contractAddress(TRON): %.*H\n",
               TRON_ADDRESS_SIZE,
               msg->txContent->contractAddress);
    }
    msg->uiType = TRON_UI_TYPE_GENERIC;

    switch (context->selectorIndex) {
        case TRANSFER_TO_VALUE:
            PRINTF("finalize to_address(EVM): %.*H\n", ADDRESS_LENGTH, context->to_address);
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
            msg->tokenLookup1 = msg->txContent->contractAddress;
            break;
        case SWAP_EXACT_TRX_FOR_TOKENS:
            // EDIT THIS: Set the total number of screen you will need.
            msg->numScreens = 2;
            // EDIT THIS: Handle this case like you wish to (i.e. maybe no additional screen needed?).
            // If the beneficiary is NOT the sender, we will need an additional screen to display it.
            // `txContent->account` is the TRON owner address (0x41 + 20-byte payload).
            if (msg->txContent != NULL) {
                PRINTF("finalize account(TRON): %.*H\n", TRON_ADDRESS_SIZE, msg->txContent->account);
            }
            PRINTF("finalize beneficiary: %.*H\n", ADDRESS_LENGTH, context->beneficiary);
            if (msg->txContent == NULL ||
                memcmp(msg->txContent->account + 1, context->beneficiary, ADDRESS_LENGTH) != 0) {
                msg->numScreens += 1;
            }

            // EDIT THIS: set `tokenLookup1` (and maybe `tokenLookup2`) to point to
            // token addresses you will info for (such as decimals, ticker...).
            msg->tokenLookup1 = context->token_received;

            break;
        case MINT:
            msg->numScreens = 2;
            msg->tokenLookup1 = msg->txContent->contractAddress;
            break;
        case SHIELDED_TRANSFER:
            msg->numScreens = 1;
            msg->tokenLookup1 = msg->txContent->contractAddress;
            break;
        case BURN:
            msg->numScreens = 2;
            msg->tokenLookup1 = msg->txContent->contractAddress;
            break;
        case BOILERPLATE_DUMMY_2:
        default:
            PRINTF("Selector index %d not supported in finalize\n", context->selectorIndex);
            msg->result = TRON_PLUGIN_RESULT_ERROR;
            return;
    }

    msg->result = TRON_PLUGIN_RESULT_OK;
}
