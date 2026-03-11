#include "plugin.h"

// Sets the first screen to display.
void handle_query_contract_id(ethQueryContractID_t *msg) {
    const context_t *context = (const context_t *) msg->pluginContext;
    // msg->name will be the upper sentence displayed on the screen.
    // msg->version will be the lower sentence displayed on the screen.

    // For the first screen, display the plugin name.
    strlcpy(msg->name, APPNAME, msg->nameLength);

    // EDIT THIS: Adapt the cases by modifying the strings you pass to `strlcpy`.
    switch (context->selectorIndex) {
        case SWAP_EXACT_ETH_FOR_TOKENS:
            strlcpy(msg->version, "Swap", msg->versionLength);
            break;
        case TRANSFER_TO_VALUE:
            strlcpy(msg->version, "Transfer", msg->versionLength);
            break;
        default:
            PRINTF("Selector index: %d not supported\n", context->selectorIndex);
            msg->result = TRON_PLUGIN_RESULT_ERROR;
            return;
    }

    // Return valid status.
    msg->result = TRON_PLUGIN_RESULT_OK;
}
