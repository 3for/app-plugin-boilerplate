# ****************************************************************************
#    Ledger TRON Plugin Boilerplate
#    (c) 2023 Ledger SAS.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
# ****************************************************************************

# EDIT THIS: Application name
APPNAME = "PluginBoilerplate"

# Application version
APPVERSION_M = 1
APPVERSION_N = 0
APPVERSION_P = 0

TRON_PROTOCOL_DIR ?= ethereum-plugin-sdk/protocol
PROTO_PY_OUT_DIR ?= build/proto
PYTHON ?= python3
GOOGLE_API_PROTO_DIR ?= ethereum-plugin-sdk/.generated/googleapis
GOOGLE_API_PROTO_SUBDIR := $(GOOGLE_API_PROTO_DIR)/google/api
GOOGLE_API_PROTO_BASE_URL ?= https://raw.githubusercontent.com/googleapis/googleapis/master/google/api
TRON_CORE_PROTO_FILES := $(wildcard $(TRON_PROTOCOL_DIR)/core/*.proto) \
	$(wildcard $(TRON_PROTOCOL_DIR)/core/contract/*.proto)
TRON_API_PROTO_FILES := $(wildcard $(TRON_PROTOCOL_DIR)/api/*.proto)
GOOGLE_API_PROTO_FILES := $(wildcard $(GOOGLE_API_PROTO_SUBDIR)/*.proto)
TRON_ALL_PROTO_FILES := $(TRON_CORE_PROTO_FILES) $(TRON_API_PROTO_FILES)

.PHONY: proto-deps proto-python proto-clean proto-deps-clean test-prepare

proto-deps:
	@mkdir -p "$(GOOGLE_API_PROTO_SUBDIR)"
	@for file in annotations.proto http.proto; do \
		dst="$(GOOGLE_API_PROTO_SUBDIR)/$$file"; \
		if [ ! -f "$$dst" ]; then \
			url="$(GOOGLE_API_PROTO_BASE_URL)/$$file"; \
			echo "Downloading $$url"; \
			$(PYTHON) -c 'import pathlib,sys,urllib.request; url,dst=sys.argv[1],sys.argv[2]; pathlib.Path(dst).parent.mkdir(parents=True, exist_ok=True); pathlib.Path(dst).write_bytes(urllib.request.urlopen(url, timeout=30).read())' "$$url" "$$dst" || { echo "Failed to download $$url"; exit 1; }; \
		fi; \
	done

proto-python: proto-deps
	@test -d "$(TRON_PROTOCOL_DIR)/core" || (echo "Missing $(TRON_PROTOCOL_DIR). Run: git submodule update --init --recursive"; exit 1)
	@$(PYTHON) -c "import grpc_tools.protoc" >/dev/null 2>&1 || (echo "Missing grpcio-tools. Install with: pip install grpcio-tools"; exit 1)
	@test -f "$(GOOGLE_API_PROTO_SUBDIR)/annotations.proto" || (echo "Missing $(GOOGLE_API_PROTO_SUBDIR)/annotations.proto"; exit 1)
	mkdir -p $(PROTO_PY_OUT_DIR); \
	$(PYTHON) -m grpc_tools.protoc \
		-I$(TRON_PROTOCOL_DIR) \
		-I$(GOOGLE_API_PROTO_DIR) \
		--python_out=$(PROTO_PY_OUT_DIR) \
		--grpc_python_out=$(PROTO_PY_OUT_DIR) \
		$(TRON_ALL_PROTO_FILES) \
		$(GOOGLE_API_PROTO_FILES)

proto-clean:
	rm -rf $(PROTO_PY_OUT_DIR)

proto-deps-clean:
	rm -rf $(GOOGLE_API_PROTO_DIR)

test-prepare: proto-python

NEED_BOLOS_SDK := 1
ifneq ($(MAKECMDGOALS),)
ifneq ($(filter-out proto-deps proto-python proto-clean proto-deps-clean test-prepare,$(MAKECMDGOALS)),)
NEED_BOLOS_SDK := 1
else
NEED_BOLOS_SDK := 0
endif
endif

ifeq ($(NEED_BOLOS_SDK),1)
include ethereum-plugin-sdk/standard_plugin.mk
endif

.DEFAULT_GOAL := all
