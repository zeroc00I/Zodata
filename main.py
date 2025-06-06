import xml.dom.minidom as minidom
import argparse
import sys
import json
import re
import os
import glob
from urllib.parse import urlparse
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import yaml

# --- Configuration ---
EDMX_NS = "http://docs.oasis-open.org/odata/ns/edmx"
EDM_NS = "http://docs.oasis-open.org/odata/ns/edm"

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# --- Core Logic Functions ---

def get_placeholders(req):
    placeholders = set(re.findall(r'\{([^{}]+)\}', req['url']))
    if req.get('body'):
        placeholders.update(re.findall(r'\{([^{}]+)\}', json.dumps(req['body'])))
    return sorted(list(placeholders))

def generate_requests(metadata_xml):
    try: dom = minidom.parseString(metadata_xml)
    except Exception as e: raise ValueError(f"Failed to parse XML: {e}")
    generated_requests = []
    for schema in dom.getElementsByTagNameNS(EDM_NS, 'Schema'):
        try: container = schema.getElementsByTagNameNS(EDM_NS, 'EntityContainer')[0]
        except IndexError: continue
        for es in container.getElementsByTagNameNS(EDM_NS, 'EntitySet'):
            name = es.getAttribute("Name")
            generated_requests.append({"method": "GET", "url": f"/{name}", "description": f"Get all {name}"})
            generated_requests.append({"method": "GET", "url": f"/{name}({{Id}})", "description": f"Get {name} by key"})
        for action in schema.getElementsByTagNameNS(EDM_NS, 'Action'):
            name = action.getAttribute("Name")
            body = {p.getAttribute("Name"): f"{{{p.getAttribute('Name')}}}" for p in action.getElementsByTagNameNS(EDM_NS, 'Parameter') if p.getAttribute("Name") != 'bindingParameter'}
            generated_requests.append({"method": "POST", "url": f"/{name}", "body": body, "description": f"Action {name}"})
        for function in schema.getElementsByTagNameNS(EDM_NS, 'Function'):
            name = function.getAttribute("Name")
            param_parts = [f"{p.getAttribute('Name')}={{{p.getAttribute('Name')}}}" for p in function.getElementsByTagNameNS(EDM_NS, 'Parameter') if p.getAttribute('Name') != 'bindingParameter']
            url = f"/{name}({','.join(param_parts)})" if param_parts else f"/{name}"
            generated_requests.append({"method": "GET", "url": url, "description": f"Function {name}"})
    return generated_requests

def send_http_request(task):
    method, url, headers, proxies, json_payload, is_silent = task
    results = []
    try:
        if not is_silent:
            proxy_info = f" (via proxy {proxies['http']})" if proxies else " (no proxy)"
            print(f"\n{bcolors.OKCYAN}---{bcolors.ENDC}\n{bcolors.WARNING}Executing: {method} {url}{proxy_info}{bcolors.ENDC}")
            if json_payload: print(f"{bcolors.WARNING}Payload: {json.dumps(json_payload)}{bcolors.ENDC}")

        response = requests.request(method, url, headers=headers, json=json_payload, proxies=proxies, verify=False, timeout=20)
        
        status_color = bcolors.OKGREEN if 200 <= response.status_code < 400 else bcolors.FAIL
        if is_silent: print(f"{method} {url} -> {status_color}{response.status_code}{bcolors.ENDC}")
        else:
            print(f"\n{status_color}--> STATUS: {response.status_code} {response.reason}{bcolors.ENDC}")
            print(f"{bcolors.OKCYAN}--> HEADERS:{bcolors.ENDC}"); [print(f"  {k}: {v}") for k, v in response.headers.items()]
            print(f"{bcolors.OKCYAN}--> BODY:{bcolors.ENDC}")
            try: print(json.dumps(response.json(), indent=2))
            except json.JSONDecodeError: print(response.text or "[Empty Response Body]")

        results.append((response.status_code, url, method))

        if method == 'GET' and response.status_code == 405:
            if not is_silent: print(f"{bcolors.WARNING}\n[405 Handler] Checking 'Allow' header...{bcolors.ENDC}")
            allowed_methods = [m.strip().upper() for m in response.headers.get('Allow', 'POST').split(',')]
            for new_method in allowed_methods:
                if new_method in ['DELETE', 'GET', 'OPTIONS', 'HEAD', 'TRACE']: continue
                if not is_silent: print(f"{bcolors.OKBLUE}--> [405 Handler] Trying: {new_method}{bcolors.ENDC}")
                sub_results = send_http_request((new_method, url, headers, proxies, {}, is_silent))
                results.extend(sub_results)
    except requests.exceptions.RequestException as e:
        print(f"{bcolors.FAIL}Request failed for {method} {url}: {e}{bcolors.ENDC}")
        results.append((-1, url, method))
    return results

# --- Execution Strategies ---

def build_execution_tasks(requests_data, base_url, headers, base_proxies, is_silent, value_provider, filtered_urls):
    tasks = []
    for req in requests_data:
        proxies_for_this_req = None if base_url + req['url'] in filtered_urls else base_proxies
        final_url_template = base_url + req['url']
        placeholders = get_placeholders(req)
        value_map = {p: value_provider(p, req) for p in placeholders}
        
        final_url = final_url_template
        for p_name, p_val in value_map.items():
            if p_val is None: final_url = None; break
            final_url = final_url.replace(f'{{{p_name}}}', requests.utils.quote(str(p_val)))
        if final_url is None: continue

        final_payload = {p_name: value_map.get(p_name) for p_name in req.get('body', {})} if req['method'] == 'POST' else None
        tasks.append((req['method'], final_url, headers, proxies_for_this_req, final_payload, is_silent))
    return tasks

def run_concurrently(tasks, max_threads, status_counts, progress_file):
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_task = {executor.submit(send_http_request, task): task for task in tasks}
        print(f"{bcolors.OKBLUE}Dispatching {len(future_to_task)} tasks across {max_threads} threads...{bcolors.ENDC}")
        for future in as_completed(future_to_task):
            try:
                results = future.result()
                for status, url, method in results:
                    status_counts[status] += 1
                    if progress_file: progress_file.write(f"{datetime.now().isoformat()} | {method} {url} | {status}\n"); progress_file.flush()
            except Exception as e: print(f"{bcolors.FAIL}Task generated an exception: {e}{bcolors.ENDC}")

# --- Command Handlers ---

def handle_generate_config_command(args):
    requests_data = generate_requests(args.xml_file.read())
    config_list = [{"method": r["method"], "url": r["url"], "description": r.get("description", ""), "params": {p: "# TODO" for p in get_placeholders(r)}} if get_placeholders(r) else r for r in requests_data]
    with open(args.output_file, 'w') as f: yaml.dump(config_list, f, sort_keys=False, indent=2)
    print(f"{bcolors.OKGREEN}Generated '{args.output_file}'.{bcolors.ENDC}")

def get_filtered_urls_from_progress(filter_statuses):
    """Parses the latest progress file to find URLs to filter."""
    if not filter_statuses: return set()
    
    progress_files = sorted(glob.glob("progress_*.txt"), reverse=True)
    if not progress_files:
        print(f"{bcolors.WARNING}Warning: -frs flag used, but no 'progress_*.txt' files found to read from.{bcolors.ENDC}")
        return set()
        
    latest_progress_file = progress_files[0]
    print(f"{bcolors.OKBLUE}Reading previous results from '{latest_progress_file}' to filter requests...{bcolors.ENDC}")
    
    filtered_urls = set()
    with open(latest_progress_file, 'r') as f:
        for line in f:
            parts = line.strip().split(' | ')
            if len(parts) == 3:
                try:
                    status_code = int(parts[2])
                    if status_code in filter_statuses:
                        filtered_urls.add(parts[1].split(' ', 1)[1]) # Add the URL part
                except (ValueError, IndexError):
                    continue
    print(f"Found {len(filtered_urls)} URLs with status {filter_statuses} to exclude from proxy.{bcolors.ENDC}")
    return filtered_urls

def handle_execute_command(args):
    status_counts, progress_file = defaultdict(int), None
    if not args.no_progress:
        hostname = urlparse(args.base_url).netloc.replace('.', '_').replace(':', '_')
        progress_filename = f"progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hostname}.txt"
        progress_file = open(progress_filename, 'a', encoding='utf-8')
        if not args.silent: print(f"{bcolors.OKBLUE}Logging progress to '{progress_filename}'{bcolors.ENDC}")
    
    try:
        headers = {k.strip(): v.strip() for h in args.headers for k, v in [h.split(':', 1)]} if args.headers else {}
        if headers and not args.silent: print(f"{bcolors.OKBLUE}Using custom headers: {headers}{bcolors.ENDC}")
        
        filtered_urls = get_filtered_urls_from_progress(set(args.filter_replay_status or []))
        
        requests_data = generate_requests(args.xml_file.read())
        base_proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else None
        base_url = args.base_url.rstrip('/')

        print(f"{bcolors.HEADER}\nChoose an execution strategy:{bcolors.ENDC}")
        print("[1] Interactive Mode (Cannot be run concurrently)")
        print("[2] Config File Mode (Uses 'requests.yaml')")
        print("[3] Auto-Fill Mode (Uses a single default value)")
        choice = ''
        while choice not in ['1', '2', '3']: choice = input("Enter your choice (1, 2, or 3): ")
        
        if choice == '1':
            if args.threads > 1: print(f"{bcolors.WARNING}Concurrency disabled for interactive mode.{bcolors.ENDC}")
            # Interactive mode handles its own logic, so we don't use build_tasks
            # (This is a simplified example; a real implementation might need refactoring to merge loops)
            # For now, -frs is not supported in interactive mode due to its sequential nature.
            if filtered_urls: print(f"{bcolors.WARNING}-frs flag is ignored in interactive mode.{bcolors.ENDC}")
            run_interactive_mode(requests_data, base_url, headers, base_proxies, status_counts, progress_file, args.silent)

        else:
            value_provider = None
            if choice == '2':
                if not os.path.exists("requests.yaml"): print(f"{bcolors.FAIL}Error: 'requests.yaml' not found.{bcolors.ENDC}"); return
                with open("requests.yaml", 'r') as f: config_data = yaml.safe_load(f)
                param_lookup = {req_conf['url']: req_conf.get('params', {}) for req_conf in config_data}
                def config_value_provider(p_name, req):
                    val = param_lookup.get(req['url'], {}).get(p_name)
                    return None if isinstance(val, str) and "# TODO" in val else val
                value_provider = config_value_provider

            elif choice == '3':
                default_value = input("Enter default value [1]: ") or "1"
                value_provider = lambda p_name, req: default_value
            
            tasks = build_execution_tasks(requests_data, base_url, headers, base_proxies, args.silent, value_provider, filtered_urls)
            run_concurrently(tasks, args.threads, status_counts, progress_file)

    finally:
        if progress_file: progress_file.close()
        print(f"\n{bcolors.HEADER}--- Execution Summary ---{bcolors.ENDC}")
        if not status_counts: print("No requests were completed.")
        else:
            for code, count in sorted(status_counts.items()):
                color = bcolors.FAIL if code < 0 or code >= 400 else bcolors.OKGREEN
                status_text = "FAILED" if code < 0 else f"Status {code}"
                print(f"{status_text}: {color}{count} requests{bcolors.ENDC}")

def run_interactive_mode(requests_data, base_url, headers, proxies, status_counts, progress_file, is_silent):
    # This mode remains sequential and doesn't support the -frs flag for simplicity.
    # A more advanced implementation would need to refactor the request loop.
    print(f"\n{bcolors.HEADER}Starting Interactive Mode...{bcolors.ENDC}")
    known_values, values_filepath = {}, "values.yaml"
    if os.path.exists(values_filepath):
        with open(values_filepath, 'r') as f: known_values = yaml.safe_load(f) or {}
        print(f"{bcolors.OKGREEN}Loaded {len(known_values)} saved values from '{values_filepath}'{bcolors.ENDC}")

    for i, req in enumerate(requests_data):
        if not is_silent:
            print(f"\n{bcolors.HEADER}--- Request {i+1}/{len(requests_data)}: {req.get('description')} ---{bcolors.ENDC}")
        value_map = {p: known_values.get(p) or input(f"  - Enter value for {bcolors.BOLD}{p}{bcolors.ENDC}: ") for p in get_placeholders(req)}
        known_values.update(value_map)

        if not is_silent:
            action = input(f"Execute this request? (y/n/skip all): ").lower()
            if action == 'skip all': break
            if action != 'y': print("Skipped."); continue

        final_url = base_url + req['url']
        for p_name, p_val in value_map.items(): final_url = final_url.replace(f'{{{p_name}}}', requests.utils.quote(str(p_val)))
        
        final_payload = {p_name: value_map.get(p_name) for p_name in req.get('body', {})} if req['method'] == 'POST' else None
        
        results = send_http_request((req['method'], final_url, headers, proxies, final_payload, is_silent))
        for status, url, method in results:
            status_counts[status] += 1
            if progress_file: progress_file.write(f"{datetime.now().isoformat()} | {method} {url} | {status}\n"); progress_file.flush()

    with open(values_filepath, 'w') as f: yaml.dump(known_values, f, sort_keys=True)
    print(f"\n{bcolors.OKGREEN}Session values saved/updated in '{values_filepath}'{bcolors.ENDC}")

def main():
    parser = argparse.ArgumentParser(description="OData endpoint testing tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_gen = subparsers.add_parser("generate-config", help="Generate 'requests.yaml'.")
    p_gen.add_argument("xml_file", type=argparse.FileType('r', encoding='utf-8'), help="OData metadata XML.")
    p_gen.add_argument("-o", "--output-file", default="requests.yaml", help="Output config file.")
    p_gen.set_defaults(func=handle_generate_config_command)

    p_exec = subparsers.add_parser("execute", help="Execute requests against an endpoint.")
    p_exec.add_argument("xml_file", type=argparse.FileType('r', encoding='utf-8'), help="OData metadata XML.")
    p_exec.add_argument("-u", "--base-url", required=True, help="Base URL of the OData service.")
    p_exec.add_argument("-p", "--proxy", help="Proxy (e.g., 'http://127.0.0.1:8080').")
    p_exec.add_argument("-t", "--threads", type=int, default=1, help="Number of concurrent threads.")
    p_exec.add_argument("-H", "--headers", action="append", help="Custom headers. 'Header-Name:Value'.")
    p_exec.add_argument("-s", "--silent", action="store_true", help="Silent mode.")
    p_exec.add_argument("-np", "--no-progress", action="store_true", help="Disable progress file logging.")
    p_exec.add_argument("-frs", "--filter-replay-status", type=int, nargs='+', help="Status codes to filter from proxy replay (e.g., 404 500). Requires a previous progress file.")
    p_exec.set_defaults(func=handle_execute_command)
    
    requests.packages.urllib3.disable_warnings()
    
    try: args = parser.parse_args(); args.func(args)
    except Exception as e: print(f"{bcolors.FAIL}\nAn error occurred: {e}{bcolors.ENDC}", file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
