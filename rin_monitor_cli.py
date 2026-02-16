#!/usr/bin/env python3

"""
RegInfo CLI

"""

import os
import sys
import hashlib
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import json
import difflib
import re
from bs4 import BeautifulSoup






class RINMonitor:
    def __init__(self, config_file='config.json'):

        self.config_file = config_file
        self.config = self.load_config()
        self.data_dir = Path(self.config.get('data_directory', 'reginfo_data'))
        self.data_dir.mkdir(exist_ok=True)








    def load_config(self):

        if not os.path.exists(self.config_file):
            print(f"Error: No Configuration file '{self.config_file}'")
            print("Creating default config.json...")
            return self.create_default_config()
        
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def create_default_config(self):

        default_config = {
            "rins": [],
            "data_directory": "reginfo_data",
            "keep_files": 2,
            "email": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "from_address": "",
                "to_address": ""
            }
        }







    def get_available_agendas(self):

        try:
            url = "https://www.reginfo.gov/public/do/eAgendaXmlReport"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            pubids = set()
            




            nav_links = soup.find_all('a', class_='pageSubNav')
            for link in nav_links:
                href = link.get('href', '')
                match = re.search(r'REGINFO_RIN_DATA_(\d{6})\.xml', href)
                if match:
                    pubid = match.group(1)
                    if len(pubid) == 6 and pubid.endswith(('04', '10')):
                        year = int(pubid[:4])
                        if 2020 <= year <= 2030:
                            pubids.add(pubid)
            
            if pubids:
                sorted_pubids = sorted(list(pubids), reverse=True)
                return sorted_pubids
            else:
                return self.generate_default_pubids()
            
        except Exception as e:
            print(f"Could not ping RegInfo.gov: {e}")
            return self.generate_default_pubids()

    
    def build_rin_xml_url(self, rin, pubid):

        return f"https://www.reginfo.gov/public/do/eAgendaViewRule?pubId={pubid}&RIN={rin}&operation=OPERATION_EXPORT_XML"
    




    def fetch_rin_xml(self, rin, pubid):

        url = self.build_rin_xml_url(rin, pubid)
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"  Error fetching XML: {e}")
            return None
           






           # Remove RUN_DATE 


    def normalize_xml_for_comparison(self, content):

        content = re.sub(r'\s+RUN_DATE=["\'][^"\']*["\']', '', content)
        content = re.sub(r'\s+run_date=["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
        
        content = re.sub(r'\s+RUNDATE=["\'][^"\']*["\']', '', content)
        content = re.sub(r'\s+rundate=["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
        
        content = re.sub(r'\s+timestamp=["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\s+generated=["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        
        return content
    
    def get_content_hash(self, content):
        normalized = self.normalize_xml_for_comparison(content)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    








    def save_rin_xml(self, rin, pubid, content):
        rin_dir = self.data_dir / rin
        rin_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = rin_dir / f"rin_{rin}_{pubid}_{timestamp}.xml"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        








        keep_count = self.config.get('keep_files', 2)
        self.cleanup_old_files(rin, keep_count)
        
        return filename








    def cleanup_old_files(self, rin, keep_count=2):
        rin_dir = self.data_dir / rin
        
        if not rin_dir.exists():
            return
        
        pattern = f"rin_{rin}_*.xml"
        files = sorted(rin_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
        
        files_to_delete = files[keep_count:]
        
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                print(f"    Deleted old file: {file_path.name}")
            except Exception as e:
                print(f"    Error deleting {file_path.name}: {e}")
    





    def get_latest_file_for_rin(self, rin):
        rin_dir = self.data_dir / rin
        
        if not rin_dir.exists():
            return None, None
        
        pattern = f"rin_{rin}_*.xml"
        files = sorted(rin_dir.glob(pattern), reverse=True)
        
        if not files:
            return None, None
        
        latest_file = files[0]
        match = re.search(r'rin_[^_]+_(\d{6})_', latest_file.name)
        if match:
            pubid = match.group(1)
            return pubid, latest_file
        
        return None, latest_file
    







    def compare_xml(self, old_content, new_content):
        old_normalized = self.normalize_xml_for_comparison(old_content)
        new_normalized = self.normalize_xml_for_comparison(new_content)
        
        old_lines = old_normalized.splitlines(keepends=True)
        new_lines = new_normalized.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            old_lines, 
            new_lines,
            fromfile='Previous',
            tofile='Current',
            lineterm=''
        ))
        
        return ''.join(diff)
    





    def send_email_notification(self, rin, old_pubid, new_pubid, diff_text, old_file, new_file):
        smtp_config = self.config['email']
        
        if not smtp_config.get('username') or not smtp_config.get('password'):
            print("    Email not configured - skipping notification")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'RegInfo RIN {rin} Change: {old_pubid} → {new_pubid}'
        msg['From'] = smtp_config['from_address']
        msg['To'] = smtp_config['to_address']
        








        text_content = f"""
RegInfo Monitor Alert
=========================

RIN: {rin}
Change: {old_pubid} → {new_pubid}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

View XML:
Previous: https://www.reginfo.gov/public/do/eAgendaViewRule?pubId={old_pubid}&RIN={rin}&operation=OPERATION_EXPORT_XML
Current: https://www.reginfo.gov/public/do/eAgendaViewRule?pubId={new_pubid}&RIN={rin}&operation=OPERATION_EXPORT_XML

Changes (first 5000 chars):
{'-' * 50}
{diff_text[:5000]}
{'-' * 50}

Local files:
Previous: {old_file}
Current: {new_file}
"""
        
        html_content = f"""
<html>
<body>
    <h2>RegInfo Monitor Alert</h2>
    <h3>RIN: {rin}</h3>
    <table style="background: #f4f4f4; padding: 15px;">
        <tr><td><strong>Previous:</strong></td><td>{old_pubid}</td></tr>
        <tr><td><strong>Current:</strong></td><td>{new_pubid}</td></tr>
        <tr><td><strong>Time:</strong></td><td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
    </table>
    <h3>View XML:</h3>
    <ul>
        <li><a href="https://www.reginfo.gov/public/do/eAgendaViewRule?pubId={old_pubid}&RIN={rin}&operation=OPERATION_EXPORT_XML">Previous ({old_pubid})</a></li>
        <li><a href="https://www.reginfo.gov/public/do/eAgendaViewRule?pubId={new_pubid}&RIN={rin}&operation=OPERATION_EXPORT_XML">Current ({new_pubid})</a></li>
    </ul>
    <h3>Changes:</h3>
    <pre style="background: #f4f4f4; padding: 10px; font-size: 11px;">
{diff_text[:5000]}
    </pre>
</body>
</html>
"""
        







        
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        msg.attach(part1)
        msg.attach(part2)
        
        try:
            with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
                server.starttls()
                server.login(smtp_config['username'], smtp_config['password'])
                server.send_message(msg)
            print(f"Email sent to {smtp_config['to_address']}")
            return True
        except Exception as e:
            print(f"Email error: {e}")
            return False
    
    def monitor_rin(self, rin):
        print(f"\n  Checking RIN: {rin}")
        






        available_pubids = self.get_available_agendas()
        if not available_pubids:
            print("Could not determine available agendas")
            return False
        
        latest_pubid = available_pubids[0]
        print(f"Latest agenda: {latest_pubid}")
        




        current_xml = self.fetch_rin_xml(rin, latest_pubid)
        if not current_xml:
            print(f"Failed to fetch XML")
            return False
        





        if "not found" in current_xml.lower() or len(current_xml) < 100:
            print(f"RIN not found in agenda {latest_pubid}")
            return False
        



        previous_pubid, previous_file = self.get_latest_file_for_rin(rin)
        




        if previous_file:

            with open(previous_file, 'r', encoding='utf-8') as f:
                previous_xml = f.read()
            
            current_hash = self.get_content_hash(current_xml)
            previous_hash = self.get_content_hash(previous_xml)
            
            if current_hash != previous_hash:

                print(f"CHANGE DETECTED: {previous_pubid} → {latest_pubid}")
                
                new_file = self.save_rin_xml(rin, latest_pubid, current_xml)
                diff = self.compare_xml(previous_xml, current_xml)
                

                self.send_email_notification(rin, previous_pubid, latest_pubid, diff, previous_file, new_file)
                return True
            else:
                print(f"No changes detected")
                self.save_rin_xml(rin, latest_pubid, current_xml)
                return False
        else:
            # First run - baseline
            print(f"Saving baseline for agenda {latest_pubid}")
            self.save_rin_xml(rin, latest_pubid, current_xml)
            return False
    



    def run(self):
        print("=" * 60)
        print("RegInfo Monitor")
        print("=" * 60)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        rins = self.config.get('rins', [])
        
        if not rins:
            print("\n No RINs configured")
            return
        
        print(f"Monitoring {len(rins)} RIN(s)")
        
        changes = 0
        for rin in rins:
            if self.monitor_rin(rin):
                changes += 1
        
        print("\n" + "=" * 60)
        print(f"Complete: {changes} change(s) detected")
        print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)








def main():
    monitor = RINMonitor()
    monitor.run()


if __name__ == '__main__':
    main()
