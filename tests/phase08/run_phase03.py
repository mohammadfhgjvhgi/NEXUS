import subprocess, sys
log = open(r"M:\NEXUS\tests\phase08\phase03_out.txt", "w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-u", r"M:\NEXUS\tests\phase03\verify_exit_criteria.py"],
                        stdout=log, stderr=subprocess.STDOUT)
print("pid:", proc.pid)
