import threading
import json
import src.verifyUSFM as verifyUSFM
import os
import tempfile
import urllib.request
from urllib.parse import urlparse
from azure.servicebus import ServiceBusClient
import zipfile
import requests
import shutil

class Logger:
    progress_lock = threading.Lock()
    progress = ""
    errors = [] 
    def event_generate(self, event:str, msg:str, when:str):
        if event == "<<ScriptProgress>>":
            return
        elif event == "<<ScriptMessage>>":
            return
        elif event == "<<Error>>":
            self.errors.append(msg)
        else:
            print(f"{when}: {event} {msg}")

def scanDir(directory:str):
    verifyUSFM.config = {
        "source_dir": directory,
        "compare_dir": None,
    }
    verifyUSFM.state = verifyUSFM.State()
    verifyUSFM.suppress[9] = True
    verifyUSFM.gui = Logger()
    verifyUSFM.verifyDir(directory)
    for error in verifyUSFM.gui.errors:
        print(error)



connstr = os.environ["AzureServiceBusConnectionString"]
topicName = "WACSEvent"
subscriptionName = "LarrysScripts"

with ServiceBusClient.from_connection_string(connstr) as client:
    with client.get_subscription_receiver(topicName, subscriptionName, uamqp_transport=True) as receiver:
        for message in receiver:
            parsed = json.loads(str(message))
            parsedUrl = urlparse(parsed["RepoHtmlUrl"])
            defaultBranch = parsed["DefaultBranch"]
            user = parsed["User"]
            repo = parsed["Repo"]

            print(f"Scannning {user}/{repo}")

            repourl = f"{parsedUrl.scheme}://{parsedUrl.netloc}/api/v1/repos/{user}/{repo}/archive/{defaultBranch}.zip"
            # Get a temporary dir
            with tempfile.TemporaryDirectory() as tempdir:
                with tempfile.NamedTemporaryFile() as downloadFile:
                    response = requests.get(repourl, stream=True)
                    for chunk in response.iter_content(chunk_size=128):
                        downloadFile.write(chunk)
                    downloadFile.flush()
                    with zipfile.ZipFile(downloadFile.name) as repoZip:
                        repoZip.extractall(tempdir)

                # Unzip repo file
                scanDir(tempdir)
                shutil.rmtree(tempdir)
            receiver.complete_message(message)

