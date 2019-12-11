import os

from run_tribler import start_tribler_core

base_path = os.environ.get('CORE_BASE_PATH', os.path.join(os.path.dirname(os.path.realpath(__file__)), "TriblerGUI"))
api_port = os.environ.get('CORE_API_PORT', '8085')
start_tribler_core(base_path, api_port)