# System Call Handler Scheduler Tool

This tool is designed to interact with Cisco Unity Connection APIs to fetch, process, and resolve schedules for system call handlers. It is robust, scalable, and optimized for environments with large data sets, ensuring efficient processing and deduplication of call handler records.

## Features

- **Call Handler Management**: Retrieves and deduplicates call handlers using a composite key (DisplayName + DtmfAccessId) to ensure uniqueness.
- **Schedule Resolution**: Resolves schedules associated with system call handlers via schedule sets and their members.
- **CSV Reporting**: Outputs results to a CSV file for easy reporting and operational use.
- **Incremental XML Parsing**: Handles large XML responses efficiently to minimize memory usage.
- **Detailed Logging**: Provides debug-level logs for troubleshooting and traceability.

## Environment Variables

The tool requires a `.env` file for configuration. Below are the environment variables that must be defined:

- `CISCO_UNITY_BASE_URL` - Base URL of the Cisco Unity Connection API (e.g., `https://<hostname>:8443/vmrest`).
- `CISCO_UNITY_USERNAME` - Username for authenticating with the API.
- `CISCO_UNITY_PASSWORD` - Password for authenticating with the API.

## Future Enhancements

- Additional features to integrate more API endpoints.
- Improved reporting and error handling.
- Enhanced support for broader operational workflows.

---

This tool is ready to grow and adapt as needed to meet evolving operational requirements. Contributions and feedback are welcome!
