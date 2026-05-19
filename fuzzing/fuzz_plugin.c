#include "plugin.h"
#include "bip32_utils.h"
#include "plugin_utils.h"

// set a small size to detect possible overflows
#define NAME_LENGTH    3u
#define VERSION_LENGTH 3u

void handle_init_contract(tronPluginInitContract_t *parameters);
void handle_provide_parameter(tronPluginProvideParameter_t *parameters);
void handle_finalize(tronPluginFinalize_t *parameters);
void handle_provide_token(tronPluginProvideInfo_t *parameters);
void handle_query_contract_id(tronQueryContractID_t *parameters);
void handle_query_contract_ui(tronQueryContractUI_t *parameters);

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    tronPluginInitContract_t init_contract = {0};
    tronPluginProvideParameter_t provide_param = {0};
    tronPluginFinalize_t finalize = {0};
    tronPluginProvideInfo_t provide_info = {0};
    tronQueryContractID_t query_id = {0};
    tronQueryContractUI_t query_ui = {0};
    txContent_t content = {0};

    context_t context;
    const uint8_t address[ADDRESS_LENGTH] = {0xee, 0xee, 0xee, 0xee, 0xee, 0xee, 0xee,
                                             0xee, 0xee, 0xee, 0xee, 0xee, 0xee, 0xee,
                                             0xee, 0xee, 0xee, 0xee, 0xee, 0xee};

    // see fullAmount / fullAddress in
    char title[32] = {0};
    char msg[79] = {0};  // 2^256 is 78 digits long

    // for token lookups
    extraInfo_t item1 = {0};
    extraInfo_t item2 = {0};

    char name[NAME_LENGTH] = {0};
    char version[VERSION_LENGTH] = {0};

    // Input layout:
    //   data[0..SELECTOR_SIZE)               : selector hint (mapped to one of SELECTORS[])
    //   data[SELECTOR_SIZE..+sizeof(content)): random txContent bytes
    //   data[...]                            : 32-byte ABI words streamed into handle_provide_parameter
    //   tail                                 : up to 2 extraInfo_t entries for token lookups
    if (size < SELECTOR_SIZE + sizeof(txContent_t)) {
        return 0;
    }
    memcpy(&content, data + SELECTOR_SIZE, sizeof(txContent_t));

    // Make `contractAddress` look like a valid TRON address (0x41 prefix) so
    // set_contract_ui() can proceed past its prefix check during the UI loop.
    content.contractAddress[0] = 0x41;

    // Bias the selector to one of the known SELECTORS so that handle_init_contract
    // accepts the input and the per-selector code paths get exercised. Without
    // this bias, random 4-byte selectors are rejected ~99.999% of the time.
    uint8_t selector_bytes[SELECTOR_SIZE];
    uint32_t sel_value = SELECTORS[data[0] % SELECTOR_COUNT];
    selector_bytes[0] = (uint8_t) ((sel_value >> 24) & 0xff);
    selector_bytes[1] = (uint8_t) ((sel_value >> 16) & 0xff);
    selector_bytes[2] = (uint8_t) ((sel_value >> 8) & 0xff);
    selector_bytes[3] = (uint8_t) (sel_value & 0xff);

    // Use path: m/44'/195'/0'/0/0
    bip32_path_t bip32;
    bip32.length = 5;
    bip32.indices[0] = 44 | 0x80000000;
    bip32.indices[1] = 195 | 0x80000000;
    bip32.indices[2] = 0 | 0x80000000;
    bip32.indices[3] = 0;
    bip32.indices[4] = 0;

    init_contract.interfaceVersion = TRON_PLUGIN_INTERFACE_VERSION_LATEST;
    init_contract.selector = selector_bytes;
    init_contract.txContent = &content;
    init_contract.pluginContext = (uint8_t *) &context;
    init_contract.pluginContextLength = sizeof(context);
    init_contract.bip32 = &bip32;
    init_contract.dataSize = size;

    handle_init_contract(&init_contract);
    if (init_contract.result != TRON_PLUGIN_RESULT_OK) {
        return 0;
    }

    // Stream ABI parameters. Per SDK contract, `parameterOffset` is measured
    // from the start of the calldata and starts at SELECTOR_SIZE for the first
    // 32-byte word. The read cursor advances through `data` independently so
    // we can reserve trailing bytes for the extraInfo_t entries below.
    size_t read_cursor = SELECTOR_SIZE + sizeof(txContent_t);
    uint32_t param_offset = SELECTOR_SIZE;
    while (size - read_cursor >= PARAMETER_LENGTH + sizeof(extraInfo_t) * 2) {
        provide_param.parameter = data + read_cursor;
        provide_param.parameterOffset = param_offset;
        provide_param.parameter_size = PARAMETER_LENGTH;
        provide_param.pluginContext = (uint8_t *) &context;
        provide_param.txContent = &content;
        handle_provide_parameter(&provide_param);
        if (provide_param.result != TRON_PLUGIN_RESULT_OK) {
            return 0;
        }
        read_cursor += PARAMETER_LENGTH;
        param_offset += PARAMETER_LENGTH;
    }

    finalize.pluginContext = (uint8_t *) &context;
    finalize.address = address;
    finalize.txContent = &content;
    handle_finalize(&finalize);
    if (finalize.result != TRON_PLUGIN_RESULT_OK) {
        return 0;
    }

    if (finalize.tokenLookup1 || finalize.tokenLookup2) {
        provide_info.pluginContext = (uint8_t *) &context;
        provide_info.txContent = &content;
        if (finalize.tokenLookup1) {
            if (size - read_cursor >= sizeof(extraInfo_t)) {
                provide_info.item1 = &item1;

                memcpy(provide_info.item1, data + read_cursor, sizeof(extraInfo_t));
                provide_info.item1->token.ticker[MAX_TICKER_LEN - 1] = '\0';
                read_cursor += sizeof(extraInfo_t);
            }
        }

        if (finalize.tokenLookup2) {
            if (size - read_cursor >= sizeof(extraInfo_t)) {
                provide_info.item2 = &item2;

                memcpy(provide_info.item2, data + read_cursor, sizeof(extraInfo_t));
                provide_info.item2->token.ticker[MAX_TICKER_LEN - 1] = '\0';
                read_cursor += sizeof(extraInfo_t);
            }
        }

        handle_provide_token(&provide_info);
        if (provide_info.result != TRON_PLUGIN_RESULT_OK) {
            return 0;
        }
    }

    query_id.pluginContext = (uint8_t *) &context;
    query_id.txContent = &content;
    query_id.name = name;
    query_id.nameLength = sizeof(name);
    query_id.version = version;
    query_id.versionLength = sizeof(version);
    handle_query_contract_id(&query_id);

    if (query_id.result != TRON_PLUGIN_RESULT_OK) {
        return 0;
    }

    printf("name:    %s\n", query_id.name);
    printf("version: %s\n", query_id.version);

    for (int screen = 0; screen < finalize.numScreens + provide_info.additionalScreens; screen++) {
        query_ui.title = title;
        query_ui.titleLength = sizeof(title);
        query_ui.msg = msg;
        query_ui.msgLength = sizeof(msg);
        query_ui.pluginContext = (uint8_t *) &context;
        query_ui.txContent = &content;
        strlcpy(query_ui.network_ticker, "TRX", sizeof(query_ui.network_ticker));

        query_ui.screenIndex = screen;
        handle_query_contract_ui(&query_ui);
        if (query_ui.result != TRON_PLUGIN_RESULT_OK) {
            return 0;
        }
        printf("%s: %s\n", title, msg);
    }

    return 0;
}
