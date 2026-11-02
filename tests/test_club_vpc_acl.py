"""Windows owner and private-DACL policy; native ACL I/O is isolated from policy."""
import json
import pytest
from test_club_host_one_shot import PWSH,ROOT,ps,quote

pytestmark=pytest.mark.skipif(not PWSH,reason='PowerShell runtime unavailable')
SCRIPT=ROOT/'deploy/docker/club-vpc-reconnect.ps1'
USER='S-1-5-21-111-222-333-1001'
ADMINS='S-1-5-32-544'
SYSTEM='S-1-5-18'

def functions(script=SCRIPT):
 return "$ErrorActionPreference='Stop';$t=$null;$e=$null;$a=[Management.Automation.Language.Parser]::ParseFile("+quote(script)+",[ref]$t,[ref]$e);if($e.Count){throw 'parse'};foreach($f in $a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$true)){. ([scriptblock]::Create($f.Extent.Text))}\n"

@pytest.mark.parametrize('script',[SCRIPT,ROOT/'deploy/docker/club-vpc-deploy.ps1'])
@pytest.mark.parametrize('owner,protected,root,rules,expected',[
 (USER,True,True,[USER,ADMINS,SYSTEM],True),
 (ADMINS,True,True,[USER,ADMINS,SYSTEM],True),
 (SYSTEM,False,False,[USER,ADMINS,SYSTEM],True),
 (ADMINS,False,False,[USER,ADMINS,SYSTEM],True),
 (ADMINS,False,True,[USER,ADMINS,SYSTEM],False),
 ('S-1-5-21-111-222-333-1002',True,True,[USER,ADMINS,SYSTEM],False),
 (ADMINS,True,True,[USER,ADMINS,SYSTEM,'S-1-1-0'],False),
 (SYSTEM,True,True,[USER,ADMINS,SYSTEM,'S-1-5-11'],False),
 (USER,True,True,[],False),
 (USER,True,True,[ADMINS,SYSTEM],False),
])
def test_owner_is_not_confused_with_effective_private_access(tmp_path,script,owner,protected,root,rules,expected):
 snapshot={'owner':owner,'protected':protected,'rules':[{'sid':s,'allow':True} for s in rules]}
 command=functions(script)+"$s="+quote(json.dumps(snapshot))+"|ConvertFrom-Json;Write-Output (Test-VpcPrivateAcl $s "+quote(USER)+' '+('$true' if root else '$false')+')'
 r=ps(tmp_path,command)
 assert r.returncode==0,r.stdout+r.stderr
 assert r.stdout.strip()==str(expected),r.stdout+r.stderr
