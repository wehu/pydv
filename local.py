from subprocess import Popen, PIPE
import shlex
from os import path 

class Local:

    def __init__(self, host, port):
        self.agent_ids = {}
        self.host = host
        self.port = port

    def spawn_agent(self, agent_id):
        d = path.dirname(__file__)
        cmd = "{}/agent.py -m {} -p {} -i {}".format(d, self.host, self.port, agent_id)
        args = shlex.split(cmd)
        p = Popen(args, stdout=PIPE, stderr=PIPE)
        self.agent_ids[agent_id] = p

    def kill_agent(self, agent_id):
        if agent_id in self.agent_ids:
            p = self.agent_ids[agent_id]
            p.terminate()
            del self.agent_ids[agent_id]
