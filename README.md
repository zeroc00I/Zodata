[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) <!-- Assuming MIT, adjust if needed -->

Zodata is a Python-based command-line tool designed to help you discover, understand, and test OData endpoints. 

It parses OData `$metadata` XML to automatically generate a list of possible requests (EntitySets, Actions, Functions) and allows you to execute them against a target service with various configurations.

## Features

*   **Metadata-Driven Request Generation:** Automatically parses OData `$metadata` XML to discover EntitySets, Actions, and Functions.
*   **Configurable Execution:**
    *   Generates a `requests.yaml` file to pre-configure parameters for requests.
    *   Supports custom HTTP headers.
    *   Supports HTTP/HTTPS proxy for request inspection or routing.
*   **Multiple Execution Modes:**
    *   **Interactive Mode:** Prompts for parameter values for each request and saves them for future sessions.
    *   **Config File Mode:** Uses values defined in `requests.yaml`.
    *   **Auto-Fill Mode:** Uses a single default value for all parameters.
*   **Concurrent Execution:** Utilizes threading to send multiple requests concurrently for faster testing.
*   **Progress Logging:** Creates a timestamped progress file logging each request, its URL, and the status code.
*   **405 Method Not Allowed Handling:** If a GET request returns a 405, Zodata checks the `Allow` header and attempts to re-send the request with allowed methods (e.g., POST).
*   **Replay Filtering (`-frs`):** Allows excluding certain URLs (based on status codes from previous runs) from being sent through the proxy during subsequent runs, useful for focusing on new or problematic endpoints.
*   **Colored Console Output:** Provides clear, color-coded feedback for request execution.

## Why Not Just Use OData Explorer (Burp Plugin) (or similar tools)?
- While GUI tools and plugins like PortSwigger's "OData Explorer" for Burp Suite are excellent for quick visual exploration and interaction with OData services, Zodata was born out of a specific need encountered during bug bounty hunting.
- I came across an OData $metadata endpoint that served an XML file with almost 300,000 characters (check image below). Many browser-based extensions, and even some dedicated tools or plugins, can struggle significantly or outright fail to parse and handle such a large metadata document due to memory constraints or processing limitations inherent in their environment.
- Faced with this challenge, I needed a robust and efficient way to quickly parse this massive metadata file and identify potential endpoints for testing. Zodata was rapidly developed as a command-line solution precisely to address this scenario. Its Python-based backend, focused on direct XML parsing (using xml.dom.minidom) and streamlined processing, allows it to handle very large metadata files effectively where other tools might falter or become unresponsive.

<table>
  <tr>
    <td style="padding: 5px;"><img src="https://github.com/user-attachments/assets/abde0849-b0f6-44a1-80d7-798ba0991794" alt="Image showing tool struggling with large file" width="500"/></td>
    <td style="padding: 5px;"><img src="https://github.com/user-attachments/assets/f60c70f5-ab2c-47a5-b32a-e40980059547" alt="Image showing large metadata file" width="500"/></td>
  </tr>
</table>

## Prerequisites

*   Python 3.7+
*   `pip` (Python package installer)

## Installation

1.  **Clone the repository (or download the script):**
    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```
    (If you only have the script, save it as `zodata.py`)

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    (If you don't have `requirements.txt`, manually install: `pip install requests PyYAML`)

## Usage

Zodata has two main commands: `generate-config` and `execute`.

```bash
python zodata.py -h
```

### 1. `generate-config`

This command parses the OData metadata XML file and generates a `requests.yaml` configuration file. This file lists all discoverable endpoints and provides placeholders for their parameters.

```bash
python zodata.py generate-config <metadata_xml_file> [options]
```

**Arguments:**
*   `metadata_xml_file`: Path to the OData metadata XML file (e.g., `metadata.xml`).

**Options:**
*   `-o, --output-file <filename>`: Name of the output configuration file (default: `requests.yaml`).

**Example:**
```bash
python zodata.py generate-config metadata.xml -o my_service_requests.yaml
```
This will create `my_service_requests.yaml`. You should then edit this file to provide actual values for the `# TODO` parameters.

### `requests.yaml` File Structure

The generated `requests.yaml` will look something like this:

```yaml
- method: GET
  url: /EntitySetName
  description: Get all EntitySetName
- method: GET
  url: /EntitySetName({Id})
  description: Get EntitySetName by key
  params:
    Id: "# TODO"
- method: POST
  url: /ActionName
  body:
    Param1: "{Param1}"
    Param2: "{Param2}"
  description: Action ActionName
  params:
    Param1: "# TODO"
    Param2: "# TODO"
- method: GET
  url: /FunctionName(ParamA={ParamA},ParamB={ParamB})
  description: Function FunctionName
  params:
    ParamA: "# TODO"
    ParamB: "# TODO"
```
Edit the `# TODO` values with appropriate test data.

### 2. `execute`

This command executes the requests (derived from the metadata XML) against the specified base URL. It offers different modes for providing parameter values.

```bash
python zodata.py execute <metadata_xml_file> -u <base_url> [options]
```

**Arguments:**
*   `metadata_xml_file`: Path to the OData metadata XML file.
*   `-u, --base-url <url>`: **Required.** The base URL of the OData service (e.g., `https://api.example.com/odata/v4`).

**Options:**
*   `-p, --proxy <proxy_url>`: Proxy server to use (e.g., `http://127.0.0.1:8080`).
*   `-t, --threads <number>`: Number of concurrent threads for sending requests (default: 1).
*   `-H, --headers "Header-Name:Value"`: Custom headers to include in requests. Can be specified multiple times (e.g., `-H "Authorization: Bearer <token>" -H "X-Custom: Test"`).
*   `-s, --silent`: Silent mode. Suppresses detailed request/response output, only showing summary status.
*   `-np, --no-progress`: Disable logging to a progress file.
*   `-frs, --filter-replay-status <status_codes...>`: List of HTTP status codes (e.g., `404 500`). If a URL in a previous progress file (e.g., `progress_*.txt`) resulted in one of these statuses, it will NOT be sent through the proxy in the current run (it will be sent directly). This is useful for avoiding re-proxying known non-existent or erroring endpoints when using tools like Burp Suite.

**Execution Modes (Prompted after running `execute`):**

1.  **[1] Interactive Mode:**
    *   Prompts you to enter values for each placeholder (e.g., `{Id}`, `{Param1}`) interactively.
    *   Saves entered values to `values.yaml` for reuse in subsequent interactive sessions.
    *   Concurrency is disabled in this mode.
    *   The `-frs` flag is currently ignored in this mode.
2.  **[2] Config File Mode:**
    *   Reads parameter values from the `requests.yaml` file (or the file specified during `generate-config`).
    *   Ensure `requests.yaml` exists and parameters are filled.
3.  **[3] Auto-Fill Mode:**
    *   Prompts for a single default value that will be used for all placeholders.

### Example Workflow

1.  **Get OData Metadata:**
    Save the OData service's `$metadata` to a file (e.g., `metadata.xml`). You can usually get this by navigating to `https://your-odata-service/$metadata` in a browser and saving the page source.

2.  **Generate Configuration:**
    ```bash
    python zodata.py generate-config metadata.xml
    ```
    This creates `requests.yaml`.

3.  **Edit `requests.yaml`:**
    Open `requests.yaml` and fill in the `# TODO` values for parameters you want to test with specific data.

4.  **Execute Requests:**
    *   **Using Config File Mode (recommended for non-interactive testing):**
        ```bash
        python zodata.py execute metadata.xml -u "https://your-odata-service/api" -t 5 -p "http://127.0.0.1:8080"
        ```
        (Then choose option `[2]` when prompted)

    *   **Using Interactive Mode:**
        ```bash
        python zodata.py execute metadata.xml -u "https://your-odata-service/api"
        ```
        (Then choose option `[1]` when prompted)

    *   **Using Auto-Fill Mode:**
        ```bash
        python zodata.py execute metadata.xml -u "https://your-odata-service/api" -t 10
        ```
        (Then choose option `[3]` and provide a default value like "1" or "test")

5.  **Review Output:**
    *   Check the console for request details, responses, and the final summary.
    *   Inspect the generated `progress_<timestamp>_<hostname>.txt` file for a log of all requests and their status codes.
    *   If in interactive mode, `values.yaml` will be updated/created.

## Progress File

When execution starts (unless `-np` is used), a progress file named `progress_<timestamp>_<hostname>.txt` is created. It logs:
`YYYY-MM-DDTHH:MM:SS.ffffff | METHOD /url/path | STATUS_CODE`

Example:
```
2023-10-27T10:30:00.123456 | GET /Users | 200
2023-10-27T10:30:01.654321 | GET /Users({Id}) | 404
```
This file is used by the `-frs` option in subsequent runs.

---

**What is Zodata?**

Zodata is a specialized command-line utility built in Python, designed to streamline the process of interacting with and testing OData (Open Data Protocol) services. By leveraging an OData service's metadata document (`$metadata` XML), Zodata automatically discovers available data entities (EntitySets), callable operations (Actions), and queryable functions (Functions). It then empowers users to execute HTTP requests against these discovered endpoints with a high degree of control and automation.

**Why use Zodata?**

*   **Automated Discovery:** Eliminates the manual effort of dissecting OData metadata to identify testable endpoints. Zodata intelligently parses the XML and prepares a comprehensive list of potential requests.
*   **Simplified Testing:** Provides a structured way to test various aspects of an OData API, from basic data retrieval (GET on EntitySets) to complex operations involving POST requests with payloads (Actions) and parameterized function calls.
*   **Flexible Parameterization:** Offers multiple modes for supplying parameters to requests:
    *   **Interactive Mode:** Ideal for exploratory testing or when specific, dynamic values are needed. It remembers values across sessions.
    *   **Configuration File (`requests.yaml`):** Perfect for repeatable test suites and defining complex parameter sets.
    *   **Auto-Fill Mode:** Useful for quick smoke tests or when parameter values are less critical.
*   **Security Testing Aid:** With proxy support (e.g., for Burp Suite or OWASP ZAP) and custom header injection, Zodata can be a valuable tool in security assessments of OData services.
*   **Efficient Workflow:** Features like concurrent request execution, progress logging, and intelligent handling of common HTTP responses (like 405 Method Not Allowed) accelerate the testing cycle. The replay filtering (`-frs`) feature is particularly useful for iterative testing, allowing users to focus proxy traffic on new or changed endpoints by skipping already-tested ones that returned specific statuses.
*   **Insight into API Behavior:** Verbose output options provide detailed information about HTTP requests and responses, helping users understand how the OData service behaves.

**Core Functionality:**

1.  **Metadata Parsing:** Reads an OData `$metadata` XML file to identify:
    *   `EntitySet` elements: Generates GET requests for fetching all entities and a specific entity by key (e.g., `GET /Users`, `GET /Users({Id})`).
    *   `Action` elements: Generates POST requests, constructing a template JSON body based on defined parameters (e.g., `POST /CreateUser` with a body like `{"UserName": "{UserName}", "Email": "{Email}"}`).
    *   `Function` elements: Generates GET requests, forming URL query parameters or path segments based on defined function parameters (e.g., `GET /GetUsersByRole(Role={Role})`).

2.  **Request Execution Engine:**
    *   Constructs and sends HTTP requests (GET, POST) to the target OData service.
    *   Manages parameter substitution in URLs and request bodies.
    *   Integrates with HTTP/HTTPS proxies.
    *   Allows adding custom HTTP headers.
    *   Executes requests concurrently using a thread pool.

3.  **User Interaction & Configuration:**
    *   **Command-Line Interface:** Intuitive commands for generating configuration and executing tests.
    *   **`requests.yaml`:** A user-editable YAML file for pre-defining request parameters, enhancing test automation and repeatability.
    *   **`values.yaml`:** Stores values entered during interactive sessions for future use.

4.  **Reporting & Logging:**
    *   Provides real-time, color-coded console output of request execution.
    *   Generates a detailed `progress_*.txt` file, logging each request's method, URL, and resulting HTTP status code, facilitating review and debugging.

**Typical Usage Flow:**

1.  **Obtain Metadata:** Download the `$metadata` XML document from the target OData service.
2.  **Generate Base Configuration (Optional but Recommended):**
    Use `zodata generate-config <metadata.xml>` to create a `requests.yaml` file. This file will list all discovered endpoints and mark parameters as `# TODO`.
3.  **Customize Configuration:**
    Edit `requests.yaml` to fill in specific values for parameters you intend to test.
**What is Zodata?**

Zodata is a specialized command-line utility built in Python, designed to streamline the process of interacting with and testing OData (Open Data Protocol) services. By leveraging an OData service's metadata document (`$metadata` XML), Zodata automatically discovers available data entities (EntitySets), callable operations (Actions), and queryable functions (Functions). It then empowers users to execute HTTP requests against these discovered endpoints with a high degree of control and automation.

**Why use Zodata?**

*   **Automated Discovery:** Eliminates the manual effort of dissecting OData metadata to identify testable endpoints. Zodata intelligently parses the XML and prepares a comprehensive list of potential requests.
*   **Simplified Testing:** Provides a structured way to test various aspects of an OData API, from basic data retrieval (GET on EntitySets) to complex operations involving POST requests with payloads (Actions) and parameterized function calls.
*   **Flexible Parameterization:** Offers multiple modes for supplying parameters to requests:
    *   **Interactive Mode:** Ideal for exploratory testing or when specific, dynamic values are needed. It remembers values across sessions.
    *   **Configuration File (`requests.yaml`):** Perfect for repeatable test suites and defining complex parameter sets.
    *   **Auto-Fill Mode:** Useful for quick smoke tests or when parameter values are less critical.
*   **Security Testing Aid:** With proxy support (e.g., for Burp Suite or OWASP ZAP) and custom header injection, Zodata can be a valuable tool in security assessments of OData services.
*   **Efficient Workflow:** Features like concurrent request execution, progress logging, and intelligent handling of common HTTP responses (like 405 Method Not Allowed) accelerate the testing cycle. The replay filtering (`-frs`) feature is particularly useful for iterative testing, allowing users to focus proxy traffic on new or changed endpoints by skipping already-tested ones that returned specific statuses.
*   **Insight into API Behavior:** Verbose output options provide detailed information about HTTP requests and responses, helping users understand how the OData service behaves.

**Core Functionality:**

1.  **Metadata Parsing:** Reads an OData `$metadata` XML file to identify:
    *   `EntitySet` elements: Generates GET requests for fetching all entities and a specific entity by key (e.g., `GET /Users`, `GET /Users({Id})`).
    *   `Action` elements: Generates POST requests, constructing a template JSON body based on defined parameters (e.g., `POST /CreateUser` with a body like `{"UserName": "{UserName}", "Email": "{Email}"}`).
    *   `Function` elements: Generates GET requests, forming URL query parameters or path segments based on defined function parameters (e.g., `GET /GetUsersByRole(Role={Role})`).

2.  **Request Execution Engine:**
    *   Constructs and sends HTTP requests (GET, POST) to the target OData service.
    *   Manages parameter substitution in URLs and request bodies.
    *   Integrates with HTTP/HTTPS proxies.
    *   Allows adding custom HTTP headers.
    *   Executes requests concurrently using a thread pool.

3.  **User Interaction & Configuration:**
    *   **Command-Line Interface:** Intuitive commands for generating configuration and executing tests.
    *   **`requests.yaml`:** A user-editable YAML file for pre-defining request parameters, enhancing test automation and repeatability.
    *   **`values.yaml`:** Stores values entered during interactive sessions for future use.

4.  **Reporting & Logging:**
    *   Provides real-time, color-coded console output of request execution.
    *   Generates a detailed `progress_*.txt` file, logging each request's method, URL, and resulting HTTP status code, facilitating review and debugging.

**Typical Usage Flow:**

1.  **Obtain Metadata:** Download the `$metadata` XML document from the target OData service.
2.  **Generate Base Configuration (Optional but Recommended):**
    Use `zodata generate-config <metadata.xml>` to create a `requests.yaml` file. This file will list all discovered endpoints and mark parameters as `# TODO`.
3.  **Customize Configuration:**
    Edit `requests.yaml` to fill in specific values for parameters you intend to test.
**What is Zodata?**

Zodata is a specialized command-line utility built in Python, designed to streamline the process of interacting with and testing OData (Open Data Protocol) services. By leveraging an OData service's metadata document (`$metadata` XML), Zodata automatically discovers available data entities (EntitySets), callable operations (Actions), and queryable functions (Functions). It then empowers users to execute HTTP requests against these discovered endpoints with a high degree of control and automation.

**Why use Zodata?**

*   **Automated Discovery:** Eliminates the manual effort of dissecting OData metadata to identify testable endpoints. Zodata intelligently parses the XML and prepares a comprehensive list of potential requests.
*   **Simplified Testing:** Provides a structured way to test various aspects of an OData API, from basic data retrieval (GET on EntitySets) to complex operations involving POST requests with payloads (Actions) and parameterized function calls.
*   **Flexible Parameterization:** Offers multiple modes for supplying parameters to requests:
    *   **Interactive Mode:** Ideal for exploratory testing or when specific, dynamic values are needed. It remembers values across sessions.
    *   **Configuration File (`requests.yaml`):** Perfect for repeatable test suites and defining complex parameter sets.
    *   **Auto-Fill Mode:** Useful for quick smoke tests or when parameter values are less critical.
*   **Security Testing Aid:** With proxy support (e.g., for Burp Suite or OWASP ZAP) and custom header injection, Zodata can be a valuable tool in security assessments of OData services.
*   **Efficient Workflow:** Features like concurrent request execution, progress logging, and intelligent handling of common HTTP responses (like 405 Method Not Allowed) accelerate the testing cycle. The replay filtering (`-frs`) feature is particularly useful for iterative testing, allowing users to focus proxy traffic on new or changed endpoints by skipping already-tested ones that returned specific statuses.
*   **Insight into API Behavior:** Verbose output options provide detailed information about HTTP requests and responses, helping users understand how the OData service behaves.

**Core Functionality:**

1.  **Metadata Parsing:** Reads an OData `$metadata` XML file to identify:
    *   `EntitySet` elements: Generates GET requests for fetching all entities and a specific entity by key (e.g., `GET /Users`, `GET /Users({Id})`).
    *   `Action` elements: Generates POST requests, constructing a template JSON body based on defined parameters (e.g., `POST /CreateUser` with a body like `{"UserName": "{UserName}", "Email": "{Email}"}`).
    *   `Function` elements: Generates GET requests, forming URL query parameters or path segments based on defined function parameters (e.g., `GET /GetUsersByRole(Role={Role})`).

2.  **Request Execution Engine:**
    *   Constructs and sends HTTP requests (GET, POST) to the target OData service.
    *   Manages parameter substitution in URLs and request bodies.
    *   Integrates with HTTP/HTTPS proxies.
    *   Allows adding custom HTTP headers.
    *   Executes requests concurrently using a thread pool.

3.  **User Interaction & Configuration:**
    *   **Command-Line Interface:** Intuitive commands for generating configuration and executing tests.
    *   **`requests.yaml`:** A user-editable YAML file for pre-defining request parameters, enhancing test automation and repeatability.
    *   **`values.yaml`:** Stores values entered during interactive sessions for future use.

4.  **Reporting & Logging:**
    *   Provides real-time, color-coded console output of request execution.
    *   Generates a detailed `progress_*.txt` file, logging each request's method, URL, and resulting HTTP status code, facilitating review and debugging.

**Typical Usage Flow:**

1.  **Obtain Metadata:** Download the `$metadata` XML document from the target OData service.
2.  **Generate Base Configuration (Optional but Recommended):**
    Use `zodata generate-config <metadata.xml>` to create a `requests.yaml` file. This file will list all discovered endpoints and mark parameters as `# TODO`.
3.  **Customize Configuration:**
    Edit `requests.yaml` to fill in specific values for parameters you intend to test.
**What is Zodata?**

Zodata is a specialized command-line utility built in Python, designed to streamline the process of interacting with and testing OData (Open Data Protocol) services. By leveraging an OData service's metadata document (`$metadata` XML), Zodata automatically discovers available data entities (EntitySets), callable operations (Actions), and queryable functions (Functions). It then empowers users to execute HTTP requests against these discovered endpoints with a high degree of control and automation.

**Why use Zodata?**

*   **Automated Discovery:** Eliminates the manual effort of dissecting OData metadata to identify testable endpoints. Zodata intelligently parses the XML and prepares a comprehensive list of potential requests.
*   **Simplified Testing:** Provides a structured way to test various aspects of an OData API, from basic data retrieval (GET on EntitySets) to complex operations involving POST requests with payloads (Actions) and parameterized function calls.
*   **Flexible Parameterization:** Offers multiple modes for supplying parameters to requests:
    *   **Interactive Mode:** Ideal for exploratory testing or when specific, dynamic values are needed. It remembers values across sessions.
    *   **Configuration File (`requests.yaml`):** Perfect for repeatable test suites and defining complex parameter sets.
    *   **Auto-Fill Mode:** Useful for quick smoke tests or when parameter values are less critical.
*   **Security Testing Aid:** With proxy support (e.g., for Burp Suite or OWASP ZAP) and custom header injection, Zodata can be a valuable tool in security assessments of OData services.
*   **Efficient Workflow:** Features like concurrent request execution, progress logging, and intelligent handling of common HTTP responses (like 405 Method Not Allowed) accelerate the testing cycle. The replay filtering (`-frs`) feature is particularly useful for iterative testing, allowing users to focus proxy traffic on new or changed endpoints by skipping already-tested ones that returned specific statuses.
*   **Insight into API Behavior:** Verbose output options provide detailed information about HTTP requests and responses, helping users understand how the OData service behaves.

**Core Functionality:**

1.  **Metadata Parsing:** Reads an OData `$metadata` XML file to identify:
    *   `EntitySet` elements: Generates GET requests for fetching all entities and a specific entity by key (e.g., `GET /Users`, `GET /Users({Id})`).
    *   `Action` elements: Generates POST requests, constructing a template JSON body based on defined parameters (e.g., `POST /CreateUser` with a body like `{"UserName": "{UserName}", "Email": "{Email}"}`).
    *   `Function` elements: Generates GET requests, forming URL query parameters or path segments based on defined function parameters (e.g., `GET /GetUsersByRole(Role={Role})`).

2.  **Request Execution Engine:**
    *   Constructs and sends HTTP requests (GET, POST) to the target OData service.
    *   Manages parameter substitution in URLs and request bodies.
    *   Integrates with HTTP/HTTPS proxies.
    *   Allows adding custom HTTP headers.
    *   Executes requests concurrently using a thread pool.

3.  **User Interaction & Configuration:**
    *   **Command-Line Interface:** Intuitive commands for generating configuration and executing tests.
    *   **`requests.yaml`:** A user-editable YAML file for pre-defining request parameters, enhancing test automation and repeatability.
    *   **`values.yaml`:** Stores values entered during interactive sessions for future use.

4.  **Reporting & Logging:**
    *   Provides real-time, color-coded console output of request execution.
    *   Generates a detailed `progress_*.txt` file, logging each request's method, URL, and resulting HTTP status code, facilitating review and debugging.

**Typical Usage Flow:**

1.  **Obtain Metadata:** Download the `$metadata` XML document from the target OData service.
2.  **Generate Base Configuration (Optional but Recommended):**
    Use `zodata generate-config <metadata.xml>` to create a `requests.yaml` file. This file will list all discovered endpoints and mark parameters as `# TODO`.
3.  **Customize Configuration:**
    Edit `requests.yaml` to fill in specific values for parameters you intend to test.

## Thanks (Inspired by)

Xybytes (https://github.com/PortSwigger/odata-explorer/blob/main/odata_explorer.py)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an Issue.
(Consider adding guidelines for contributing if you plan to make this a larger project).

## License

This project is licensed under the MIT License - see the `LICENSE` file for details (You would need to create a `LICENSE` file with MIT license text).
If you don't have a specific license in mind, MIT is a common permissive one.

---
