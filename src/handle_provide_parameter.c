#include "plugin.h"

// EDIT THIS: Remove this function and write your own handlers!
static void handle_SWAP_EXACT_TRX_FOR_TOKENS(tronPluginProvideParameter_t *msg, context_t *context) {
    if (context->go_to_offset) {
        if (msg->parameterOffset != context->offset + SELECTOR_SIZE) {
            return;
        }
        context->go_to_offset = false;
    }
    switch (context->next_param) {
        case MIN_AMOUNT_RECEIVED:  // amountOutMin
            copy_parameter(context->amount_received,
                           msg->parameter,
                           sizeof(context->amount_received));
            context->next_param = PATH_OFFSET;
            break;
        case PATH_OFFSET:  // path
            context->offset = U2BE(msg->parameter, PARAMETER_LENGTH - 2);
            context->next_param = BENEFICIARY;
            break;
        case BENEFICIARY:  // to
            copy_address(context->beneficiary, msg->parameter, sizeof(context->beneficiary));
            context->next_param = PATH_LENGTH;
            context->go_to_offset = true;
            break;
        case PATH_LENGTH:
            context->offset = msg->parameterOffset - SELECTOR_SIZE + PARAMETER_LENGTH * 2;
            context->go_to_offset = true;
            context->next_param = TOKEN_RECEIVED;
            break;
        case TOKEN_RECEIVED:  // path[1] -> contract address of token received
            copy_address(context->token_received, msg->parameter, sizeof(context->token_received));
            context->next_param = UNEXPECTED_PARAMETER;
            break;
        // Keep this
        default:
            PRINTF("Param not supported: %d\n", context->next_param);
            msg->result = TRON_PLUGIN_RESULT_ERROR;
            break;
    }
}

// EDIT THIS: Remove this function and write your own handlers!
static void hanlde_transfer_to_value(tronPluginProvideParameter_t *msg, context_t *context) {
    if (context->go_to_offset) {
        if (msg->parameterOffset != context->offset + SELECTOR_SIZE) {
            return;
        }
        context->go_to_offset = false;
    }
    switch (context->next_param) {
        case TO_ADDRESS:  // to_address
            copy_address(context->to_address,
                           msg->parameter,
                           sizeof(context->to_address));
            context->next_param = VALUE;
            break;
        case VALUE:  // value
            copy_parameter(context->value,
                           msg->parameter,
                           sizeof(context->value));
            context->next_param = UNEXPECTED_PARAMETER;
            break;
        // Keep this
        default:
            PRINTF("Param not supported: %d\n", context->next_param);
            msg->result = TRON_PLUGIN_RESULT_ERROR;
            break;
    }
}

static void handle_mint(tronPluginProvideParameter_t *msg, context_t *context) {
    switch (context->next_param) {
        case MINT_RAW_VALUE:  // rawValue (uint256)
            copy_parameter(context->value, msg->parameter, sizeof(context->value));
            context->next_param = MINT_SKIP;
            break;
        case MINT_SKIP:
            // Remaining parameters (output[9], bindingSignature[2], c[21]) are
            // cryptographic data not displayed on screen; skip them silently.
            break;
        default:
            PRINTF("Param not supported: %d\n", context->next_param);
            msg->result = TRON_PLUGIN_RESULT_ERROR;
            break;
    }
}

static void handle_shielded_transfer(tronPluginProvideParameter_t *msg, context_t *context) {
    (void) msg;
    (void) context;
    // Shielded transfer parameters are cryptographic note data with no clear
    // amount or recipient to display. Accept each streamed ABI word.
}

static void handle_burn(tronPluginProvideParameter_t *msg, context_t *context) {
    switch (context->next_param) {
        case BURN_RAW_VALUE:
            // burn(input[10], spendAuthoritySignature[2], rawValue, ...)
            if (msg->parameterOffset != SELECTOR_SIZE + (12 * PARAMETER_LENGTH)) {
                return;
            }
            copy_parameter(context->value, msg->parameter, sizeof(context->value));
            context->next_param = BURN_SKIP;
            break;
        case BURN_SKIP:
            // Remaining parameters are shielded note/signature data not shown on screen.
            break;
        default:
            PRINTF("Param not supported: %d\n", context->next_param);
            msg->result = TRON_PLUGIN_RESULT_ERROR;
            break;
    }
}

void handle_provide_parameter(tronPluginProvideParameter_t *msg) {
    context_t *context = (context_t *) msg->pluginContext;
    // We use `%.*H`: it's a utility function to print bytes. You first give
    // the number of bytes you wish to print (in this case, `PARAMETER_LENGTH`) and then
    // the address (here `msg->parameter`).
    PRINTF("plugin provide parameter: offset %d\nBytes: %.*H\n",
           msg->parameterOffset,
           PARAMETER_LENGTH,
           msg->parameter);

    msg->result = TRON_PLUGIN_RESULT_OK;

    // EDIT THIS: adapt the cases and the names of the functions.
    switch (context->selectorIndex) {
        case TRANSFER_TO_VALUE:
            hanlde_transfer_to_value(msg, context);
            break;
        case SWAP_EXACT_TRX_FOR_TOKENS:
            handle_SWAP_EXACT_TRX_FOR_TOKENS(msg, context);
            break;
        case BOILERPLATE_DUMMY_2:
            break;
        case SHIELDED_MINT:
            handle_mint(msg, context);
            break;
        case SHIELDED_TRANSFER:
            handle_shielded_transfer(msg, context);
            break;
        case SHIELDED_BURN:
            handle_burn(msg, context);
            break;
        default:
            PRINTF("Selector Index not supported: %d\n", context->selectorIndex);
            msg->result = TRON_PLUGIN_RESULT_ERROR;
            break;
    }
}
