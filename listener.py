import sys
sys.path.append('usfmtools/src')
import threading
import json
import re
import usfmtools.src.verifyUSFM as verifyUSFM
import os
import tempfile
import urllib.request
from urllib.parse import urlparse
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.storage.blob import BlobServiceClient
import zipfile
import requests
import shutil
import logging
from typing import Optional, Callable
from azure.monitor.opentelemetry import configure_azure_monitor

class ScanResult:
    def __init__(self):
        self.results: dict = {}

    def add_error(self, book: str, chapter: str, verse: str, message: str, errorId: str):
        if book == "":
            book = "Unknown"
        if chapter == "":
            chapter = "Unknown"
        if verse == "":
            verse = "Unknown"

        if book not in self.results:
            self.results[book] = {}
        if chapter not in self.results[book]:
            self.results[book][chapter] = []
        self.results[book][chapter].append({"verse": verse, "message": message, "errorId": errorId})
    def to_json(self):
        return json.dumps(self.results)

class ResultsListener:

    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        self.result = ScanResult()
        self.progress_callback = callback
    referenceRegex = r"([A-Z1-3]{2,3})\s(\d+)(:(\d+))?"
    sourceFileRegex = r"([A-Z1-3]{2,3})\.usfm"
    progress_lock = threading.Lock()
    progress_callback: Optional[Callable[[str], None]]
    result: ScanResult
    def error(self, msg:str, errorId:float):
        matches = re.findall(self.referenceRegex, msg)
        if (len(matches) > 0):
            book = matches[0][0]
            chapter = matches[0][1]
            verse = matches[0][3]
            self.result.add_error(book, chapter, verse, msg, str(errorId))
        else:
            matches = re.findall(self.sourceFileRegex, msg)
            if (len(matches) > 0):
                book = matches[0]
                self.result.add_error(book, "Unknown", "Unknown", msg, str(errorId))
            else:
                self.result.add_error("Unknown", "Unknown", "Unknown", msg, str(errorId))

    def progress(self, msg:str):
        if self.progress_callback:
            self.progress_callback(msg)

def scan_dir(directory:str, listener: ResultsListener):
    verifyUSFM.config = {
        "source_dir": directory,
        "compare_dir": None,
    }
    verifyUSFM.state = verifyUSFM.State()
    verifyUSFM.listener = listener
    verifyUSFM.verifyDir(directory)
        

def upload_to_blob_storage(data: str, container_name: str, blob_name: str) -> None:
    connect_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    if not connect_str:
        raise ValueError("Azure Storage connection string not found")

    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    container_client = blob_service_client.get_container_client(container_name)

    # Create the container if it does not exist
    if not container_client.exists():
        container_client.create_container()
        print(f"Container created: {container_name}")

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(data, overwrite=True)
    print(f"Uploaded to blob storage: {blob_name}")


def listen_for_messages():
    app_insights_key = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if app_insights_key != None and app_insights_key != "":
        configure_azure_monitor()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    topicName = "WACSEvent"
    resultTopicName = "LintingResult"
    subscriptionName = "LarrysScripts"
    connstr = os.environ.get("Azure_ServiceBus_Connection_String")
    output_prefix = os.environ.get("OUTPUT_PREFIX")
    if not connstr:
        logger.error("No Service Bus connection string found")
        exit(1)
    with ServiceBusClient.from_connection_string(connstr) as client:
        with client.get_subscription_receiver(topicName, subscriptionName, uamqp_transport=True) as receiver:
            for message in receiver:
                parsed = json.loads(str(message))
                parsedUrl = urlparse(parsed["RepoHtmlUrl"])
                defaultBranch = parsed["DefaultBranch"]
                user = parsed["User"]
                repo = parsed["Repo"]
                id = parsed["RepoId"]
                success = True

                logger.info(f"Scanning {user}/{repo}")

                repourl = f"{parsedUrl.scheme}://{parsedUrl.netloc}/api/v1/repos/{user}/{repo}/archive/{defaultBranch}.zip"
                # Get a temporary dir
                result_logger = ResultsListener()
                result_logger.progress_callback = lambda msg: (receiver.renew_message_lock(message), None)[1]
                with tempfile.TemporaryDirectory() as tempdir:
                    with tempfile.NamedTemporaryFile() as downloadFile:
                        response = requests.get(repourl, stream=True)
                        if response.status_code != 200:
                            logger.error(f"Failed to download {user}/{repo}: {response.status_code}")
                            receiver.dead_letter_message(message, reason=f"Failed to download {user}/{repo}", error_description=f"HTTP status code {response.status_code}")
                            continue
                        for chunk in response.iter_content(chunk_size=128):
                            downloadFile.write(chunk)
                        downloadFile.flush()
                        with zipfile.ZipFile(downloadFile.name) as repoZip:
                            repoZip.extractall(tempdir)

                    # Unzip repo file
                    try:
                        scan_dir(tempdir, result_logger)
                    except Exception as e:
                        receiver.dead_letter_message(message, reason=f"Error scanning {user}/{repo}", error_description=str(e))
                        logger.error(f"Error scanning {user}/{repo}: {e}", stack_info=True)
                        #logger.exception(e)
                        success = False
                    finally:
                        shutil.rmtree(tempdir)
                if not success:
                    continue
                logger.info(f"Scanning {user}/{repo} complete")
                if len(result_logger.result.results) > 0:
                    output_path = f"{user}/{repo}.json"
                    upload_to_blob_storage(result_logger.result.to_json(), "scan-results", output_path)
                    uploaded_url = f"{output_prefix}/{output_path}"
                    with client.get_topic_sender(resultTopicName) as sender:
                        sender.send_messages(ServiceBusMessage(json.dumps({"User": user, "Repo": repo, "RepoId": id, "ResultsFileUrl": uploaded_url})))
                receiver.complete_message(message)

if __name__ == "__main__":
    listen_for_messages()

