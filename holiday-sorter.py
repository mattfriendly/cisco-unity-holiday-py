import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import os
import logging
import xml.etree.ElementTree as ET
from io import BytesIO

# Load environment variables from .env file
load_dotenv()

# Configuration from .env file
BASE_URL = os.getenv("CISCO_UNITY_BASE_URL")
USERNAME = os.getenv("CISCO_UNITY_USERNAME")
PASSWORD = os.getenv("CISCO_UNITY_PASSWORD")

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()

# Validate environment variables
if not all([BASE_URL, USERNAME, PASSWORD]):
    logger.error("Missing required environment variables. Ensure the .env file is configured correctly.")
    raise ValueError("Missing required environment variables.")

# Incremental XML parser
def parse_large_xml(xml_data, element_name):
    """
    Incrementally parses large XML data and extracts elements.
    """
    try:
        logger.debug("Starting incremental XML parsing.")
        xml_data = BytesIO(xml_data)  # Ensure data is treated as bytes
        record_count = 0
        for event, elem in ET.iterparse(xml_data, events=('end',)):
            if elem.tag.endswith(element_name):  # Handle possible namespaces
                record_count += 1
                logger.debug(f"--- Processing new record #{record_count} ---")
                record = {child.tag.split('}')[-1]: child.text for child in elem}  # Handle namespaces in tags
                logger.debug(f"Record details: {record}")
                yield record
                elem.clear()  # Free memory for processed element
        logger.debug(f"Finished processing {record_count} records.")
    except ET.ParseError as e:
        logger.error(f"Error parsing XML: {e}")

# Functions to interact with the API
def get_schedules():
    """
    Retrieves a full list of schedules and parses them incrementally.
    """
    url = f"{BASE_URL}/schedules"
    logger.debug(f"Sending request to {url}")
    try:
        response = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD), verify=False, stream=True)
        logger.debug(f"Response status code: {response.status_code}")
        if response.status_code == 200:
            logger.debug(f"Schedule API response: {response.content[:500]}...")
            logger.info("Successfully retrieved schedules.")
            return list(parse_large_xml(response.content, "Schedule"))
        else:
            logger.error(f"Error retrieving schedules: {response.status_code} - {response.text}")
            return []
    except requests.RequestException as e:
        logger.exception("Exception occurred while fetching schedules.")
        return []

def get_schedule_set_members(schedule_set_id):
    """
    Fetches the members of a specific schedule set.
    """
    url = f"{BASE_URL}/schedulesets/{schedule_set_id}/schedulesetmembers"
    logger.debug(f"Fetching schedule set members from {url}")
    try:
        response = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD), verify=False, stream=True)
        if response.status_code == 200:
            logger.debug(f"Schedule set members response: {response.content[:500]}...")
            return list(parse_large_xml(response.content, "ScheduleSetMember"))
        else:
            logger.error(f"Failed to fetch schedule set members: {response.status_code} - {response.text}")
            return []
    except requests.RequestException as e:
        logger.exception("Exception occurred while fetching schedule set members.")
        return []

def get_call_handlers():
    """
    Retrieves a list of call handlers, ensuring uniqueness based on a composite deduplication key.
    """
    url = f"{BASE_URL}/handlers/callhandlers"
    logger.debug(f"Sending request to {url}")
    try:
        response = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD), verify=False, stream=True)
        logger.debug(f"Response status code: {response.status_code}")
        if response.status_code == 200:
            logger.debug(f"Call Handlers API response: {response.content[:500]}...")
            logger.info("Successfully retrieved call handlers.")
            all_handlers = list(parse_large_xml(response.content, "Callhandler"))

            # Filter system call handlers using broader criteria
            system_handlers = [
                handler for handler in all_handlers
                if handler.get("Undeletable", "false").lower() == "true"
                or handler.get("DtmfAccessId")  # Include if DtmfAccessId is present
                or handler.get("DisplayName", "").strip().lower() in ["auto attendant", "opening greeting", "operator"]
            ]

            # Deduplicate by composite key
            unique_handlers = {}
            for handler in system_handlers:
                # Create a composite key for deduplication
                composite_key = f"{handler.get('DisplayName', '').strip().lower()}|{handler.get('DtmfAccessId', '')}"

                if composite_key not in unique_handlers:
                    unique_handlers[composite_key] = handler
                else:
                    logger.warning(
                        f"Duplicate handler detected: {handler.get('DisplayName', 'Unnamed Handler')} "
                        f"with key {composite_key}. Keeping the first instance."
                    )

            logger.info(f"Filtered {len(unique_handlers)} unique system call handlers from {len(all_handlers)} total handlers.")
            return list(unique_handlers.values())
        else:
            logger.error(f"Error retrieving call handlers: {response.status_code} - {response.text}")
            return []
    except requests.RequestException as e:
        logger.exception("Exception occurred while fetching call handlers.")
        return []

def get_all_schedule_set_members(call_handlers):
    """
    Retrieves all schedule set members for the given call handlers.
    """
    schedule_set_members_map = {}
    unique_schedule_set_ids = {handler.get("ScheduleSetObjectId") for handler in call_handlers if handler.get("ScheduleSetObjectId")}

    for schedule_set_id in unique_schedule_set_ids:
        if schedule_set_id:
            logger.debug(f"Retrieving members for ScheduleSetObjectId: {schedule_set_id}")
            members = get_schedule_set_members(schedule_set_id)
            schedule_set_members_map[schedule_set_id] = members

    return schedule_set_members_map

def resolve_schedules(call_handlers, schedules, schedule_sets, schedule_set_members_map):
    """
    Associates call handlers with resolved schedules via schedule sets and schedule set members.
    """
    logger.debug("Resolving schedules for call handlers via schedule sets and members.")
    schedule_map = {schedule['ObjectId']: schedule['DisplayName'] for schedule in schedules}
    concatenated_list = []

    for handler in call_handlers:
        handler_name = handler.get("DisplayName", "Unnamed Handler")
        schedule_set_id = handler.get("ScheduleSetObjectId")

        if not schedule_set_id:
            logger.warning(f"Call Handler '{handler_name}' has no ScheduleSetObjectId.")
            concatenated_list.append({"CallHandlerName": handler_name, "Schedule": "No Schedule"})
            continue

        # Find matching schedule set members for the ScheduleSetObjectId
        schedule_set_members = schedule_set_members_map.get(schedule_set_id, [])
        if not schedule_set_members:
            logger.warning(f"No members found for ScheduleSetObjectId '{schedule_set_id}' in Call Handler '{handler_name}'.")
            concatenated_list.append({"CallHandlerName": handler_name, "Schedule": "No Schedule"})
            continue

        # Filter and resolve schedules
        resolved_schedules = [
            schedule_map.get(member["ScheduleObjectId"], "Unknown Schedule")
            for member in schedule_set_members
            if not member.get("Exclude", "false").lower() == "true"
        ]

        if not resolved_schedules:
            logger.warning(f"No valid schedules linked to Call Handler '{handler_name}' via ScheduleSetObjectId '{schedule_set_id}'.")
            concatenated_list.append({"CallHandlerName": handler_name, "Schedule": "No Schedule"})
        else:
            concatenated_list.append({
                "CallHandlerName": handler_name,
                "Schedule": ", ".join(resolved_schedules)
            })

    logger.info("Successfully resolved and associated call handlers with schedules.")
    return concatenated_list

# Main Script Execution
if __name__ == "__main__":
    logger.info("Starting script execution.")

    # Retrieve call handlers and schedules
    call_handlers = get_call_handlers()
    schedules = get_schedules()

    if call_handlers and schedules:
        # Retrieve schedule set members
        schedule_set_members_map = get_all_schedule_set_members(call_handlers)

        # Resolve schedules for call handlers
        concatenated_list = resolve_schedules(call_handlers, schedules, [], schedule_set_members_map)

        # Display results
        logger.info("System Call Handlers and their Schedules:")
        for entry in concatenated_list:
            logger.info(f"Call Handler: {entry['CallHandlerName']}, Schedule: {entry['Schedule']}")

        # Optionally, export to a file
        output_file = "call_handlers_and_schedules.csv"
        with open(output_file, "w") as file:
            file.write("CallHandlerName,Schedule\n")
            for entry in concatenated_list:
                file.write(f"{entry['CallHandlerName']},{entry['Schedule']}\n")
            logger.info(f"Results saved to '{output_file}'")
    else:
        logger.error("Could not retrieve required data. Check logs for details.")
