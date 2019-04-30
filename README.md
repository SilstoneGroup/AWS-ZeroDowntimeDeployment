# AWS-ZeroDowntimeDeploy
Zero Downtime Deploy python script


Steps to run the script.
1. Install the dependencies via pip3 install -r requirements.txt
2. Edit task.py file to enter region, access_id and access_key. `This is for test purpose only. For production we shall use either environment variables or file paths for accessing these credentials`
3. Run the task as python3 task.py <old_ami> <new_ami>
4. Use -v for info logging
