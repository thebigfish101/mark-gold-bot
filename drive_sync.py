from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import os

class DriveSync:
    def __init__(self, local_file="mark_memory.json", drive_file_title="mark_memory.json"):
        self.local_file = local_file
        self.drive_file_title = drive_file_title
        self.drive = None
        self.file_id = None
        self._authenticate()

    def _authenticate(self):
        gauth = GoogleAuth()
        gauth.LocalWebserverAuth()
        self.drive = GoogleDrive(gauth)
        # Try finding existing file
        file_list = self.drive.ListFile({'q': f"title='{self.drive_file_title}' and trashed=false"}).GetList()
        if file_list:
            self.file_id = file_list[0]['id']

    def upload(self):
        if not self.drive:
            return
        file_metadata = {
            'title': self.drive_file_title
        }
        if self.file_id:
            file = self.drive.CreateFile({'id': self.file_id})
        else:
            file = self.drive.CreateFile(file_metadata)
        file.SetContentFile(self.local_file)
        file.Upload()
        self.file_id = file['id']
        print("✅ Memory uploaded to Google Drive")

    def download(self):
        if not self.file_id:
            print("⚠️ No memory file found on Google Drive.")
            return False
        file = self.drive.CreateFile({'id': self.file_id})
        file.GetContentFile(self.local_file)
        print("📥 Memory downloaded from Google Drive")
        return True
