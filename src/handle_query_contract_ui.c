#include "plugin.h"

// EDIT THIS: You need to adapt / remove the static functions (set_value_ui, set_contract_ui ...) to
// match what you wish to display.

// Set UI for "Value" screen.
// EDIT THIS: Adapt / remove this function to your needs.
static bool set_value_ui(ethQueryContractUI_t *msg, const context_t *context) {
    strlcpy(msg->title, "Value", msg->titleLength);

    uint8_t decimals = context->decimals;
    const char *ticker = context->ticker;

    // If the token look up failed, use the default network ticker along with the default decimals.
    if (!context->token_found) {
        decimals = SUN_TO_TRX;
        ticker = msg->network_ticker;
    }

    return amountToString(context->value,
                          sizeof(context->value),
                          decimals,
                          ticker,
                          msg->msg,
                          msg->msgLength);
}

// Set UI for "Contract" screen.
// EDIT THIS: Adapt / remove this function to your needs.
static bool set_contract_ui(ethQueryContractUI_t *msg, context_t *context) {
    (void) context;
    strlcpy(msg->title, "Contract", msg->titleLength);
    if (msg->txContent == NULL || msg->msgLength == 0) {
        return false;
    }
    PRINTF("set_contract_ui contractAddress(TRON): %.*H\n",
           TRON_ADDRESS_SIZE,
           msg->txContent->contractAddress);
    if (msg->txContent->contractAddress[0] != 0x41) {
        return false;
    }

    // Convert TRON binary address (0x41 + 20-byte payload) into Base58Check `T...`.
    char eth_address[(ADDRESS_LENGTH * 2) + 3];
    uint64_t chainid = 0;
    if (!getEthDisplayableAddress(msg->txContent->contractAddress + 1,
                                  eth_address,
                                  sizeof(eth_address),
                                  chainid)) {
        return false;
    }

    return ethToTronBase58(eth_address, msg->msg, msg->msgLength);
}

// Set UI for "To Address" screen.
// EDIT THIS: Adapt / remove this function to your needs.
static bool set_to_address_ui(ethQueryContractUI_t *msg, context_t *context) {
    strlcpy(msg->title, "To Address", msg->titleLength);
    PRINTF("set_to_address_ui to_address: %.*H\n", ADDRESS_LENGTH, context->to_address);

    // Convert the stored 20-byte EVM-style address into a TRON Base58Check string.
    char eth_address[(ADDRESS_LENGTH * 2) + 3];
    uint64_t chainid = 0;

    if (!getEthDisplayableAddress(context->to_address, eth_address, sizeof(eth_address), chainid)) {
        return false;
    }

    return ethToTronBase58(eth_address, msg->msg, msg->msgLength);
}

// Set UI for the "Send" screen.
// EDIT THIS: Adapt / remove this function to your needs.
static bool set_send_ui(ethQueryContractUI_t *msg) {
    strlcpy(msg->title, "Send", msg->titleLength);

    if (msg->txContent == NULL) {
        return false;
    }

    uint8_t amount[sizeof(uint64_t)];
    uint64_t send_amount = msg->txContent->amount[0];

    for (size_t i = 0; i < sizeof(amount); i++) {
        amount[sizeof(amount) - 1 - i] = (uint8_t) (send_amount & 0xFF);
        send_amount >>= 8;
    }

    // Converts the native TRX amount located in `amount` to its string representation and
    // copies this to `msg->msg`.
    return amountToString(amount,
                          sizeof(amount),
                          SUN_TO_TRX,
                          msg->network_ticker,
                          msg->msg,
                          msg->msgLength);
}

// Set UI for "Receive" screen.
// EDIT THIS: Adapt / remove this function to your needs.
static bool set_receive_ui(ethQueryContractUI_t *msg, const context_t *context) {
    strlcpy(msg->title, "Receive Min.", msg->titleLength);

    uint8_t decimals = context->decimals;
    const char *ticker = context->ticker;

    // If the token look up failed, use the default network ticker along with the default decimals.
    if (!context->token_found) {
        decimals = SUN_TO_TRX;
        ticker = msg->network_ticker;
    }

    return amountToString(context->amount_received,
                          sizeof(context->amount_received),
                          decimals,
                          ticker,
                          msg->msg,
                          msg->msgLength);
}

// Set UI for "Beneficiary" screen.
// EDIT THIS: Adapt / remove this function to your needs.
static bool set_beneficiary_ui(ethQueryContractUI_t *msg, context_t *context) {
    strlcpy(msg->title, "Beneficiary", msg->titleLength);

    // Convert the stored 20-byte EVM-style address into a TRON Base58Check string.
    char eth_address[(ADDRESS_LENGTH * 2) + 3];
    uint64_t chainid = 0;

    if (!getEthDisplayableAddress(context->beneficiary,
                                  eth_address,
                                  sizeof(eth_address),
                                  chainid)) {
        return false;
    }

    return ethToTronBase58(eth_address, msg->msg, msg->msgLength);
}


void handle_query_contract_ui(ethQueryContractUI_t *msg) {
    context_t *context = (context_t *) msg->pluginContext;
    bool ret = false;

    // msg->title is the upper line displayed on the device.
    // msg->msg is the lower line displayed on the device.

    // Clean the display fields.
    memset(msg->title, 0, msg->titleLength);
    memset(msg->msg, 0, msg->msgLength);

    // EDIT THIS: Adapt the cases for the screens you'd like to display.
    switch (context->selectorIndex) {
        case TRANSFER_TO_VALUE:
            switch (msg->screenIndex) {
                case 0:
                    ret = set_to_address_ui(msg, context);
                    break;
                case 1:
                    ret = set_value_ui(msg, context);
                    break;
                case 2:
                    ret = set_contract_ui(msg, context);
                    break;
                // Keep this
                default:
                    PRINTF("Received an invalid screenIndex\n");
            }
            break;
        case SWAP_EXACT_TRX_FOR_TOKENS:
            // EDIT THIS: Adapt the cases for the screens you'd like to display.
            switch (msg->screenIndex) {
                case 0:
                    ret = set_send_ui(msg);
                    break;
                case 1:
                    ret = set_receive_ui(msg, context);
                    break;
                case 2:
                    ret = set_beneficiary_ui(msg, context);
                    break;
                // Keep this
                default:
                    PRINTF("Received an invalid screenIndex\n");
            }
            break;
        case MINT:
            switch (msg->screenIndex) {
                case 0:
                    ret = set_value_ui(msg, context);
                    break;
                case 1:
                    ret = set_contract_ui(msg, context);
                    break;
                default:
                    PRINTF("Received an invalid screenIndex\n");
            }
            break;
        case SHIELDED_TRANSFER:
            switch (msg->screenIndex) {
                case 0:
                    ret = set_contract_ui(msg, context);
                    break;
                default:
                    PRINTF("Received an invalid screenIndex\n");
            }
            break;
        case BOILERPLATE_DUMMY_2:
        default:
            PRINTF("Selector index %d not supported in query_contract_ui\n", context->selectorIndex);
            break;
    }
    msg->result = ret ? TRON_PLUGIN_RESULT_OK : TRON_PLUGIN_RESULT_ERROR;
}
