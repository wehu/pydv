#!/usr/bin/env python3.4

from optparse import OptionParser
import socket
from threading import Timer, Thread
#from multiprocessing import Process, Queue
import marshal
import asyncio
from queue import Queue
import os
from subprocess import Popen, PIPE
import shlex
import signal
from os import path, rename 
import logging

from logger import logger, FORMAT, get_level

host = None
port = None
agent_id = None
out_dir = None

time_out = 60
timer = None

cmd_q = Queue()

def talk_to_server(data):
    re_try = 10
    while True:
        try:
            s = socket.socket()
            s.connect((host, port))
            try:
                s.send(data)
            finally:
                s.close()
                pass
            break
        except Exception as e:
            logger.warning(str(e))
            re_try -= 1
            if re_try > 0:
                pass
            else:
                raise e


def send_heart_beat():
    global timer

    data = {'cmd' : 'heart_beat',
            'agent_id' : agent_id}
    bs = marshal.dumps(data)
    try:
        talk_to_server(bs)
    except Exception as e:
        logger.error(e)
        logger.error("connect send heartbeat to dv.py and susicide")
        cleanup()
        exit(-1)
    timer = Timer(time_out, send_heart_beat)
    timer.start()
    

class AgentProtocal(asyncio.Protocol):

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        msg = marshal.loads(data)
        logger.debug('agent {} server received data {}'.format(agent_id, msg))
        cmd_q.put(msg)
        #self.transport.close()

server_host = None
server_port = None

def start_server(loop):
    
    #loop = asyncio.get_event_loop()

    server_host = socket.gethostname()
    server_ip = socket.gethostbyname(server_host)

    coro = loop.create_server(AgentProtocal, server_ip)
    server = loop.run_until_complete(coro)

    _, server_port = server.sockets[0].getsockname()

    cmd_q.put((server_host, server_port))
    
    loop.run_forever()

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
    
def get_cmd():
    data = {'cmd' : 'require_cmd',
            'agent_id' : agent_id,
            'agent_host' : server_host,
            'agent_port' : server_port}
    bs = marshal.dumps(data)
    talk_to_server(bs)
    cmd_spec = cmd_q.get()
    return cmd_spec

def send_status(msg):
    data = {'cmd' : 'update_status',
            'agent_id' : agent_id,
            'msg' : msg}
    bs = marshal.dumps(data)
    talk_to_server(bs)

def cmd_done(exitcode, err):
    data = {'cmd' : 'cmd_done',
            'agent_id' : agent_id,
            'exitcode' : exitcode,
            'errmsg' : err}
    bs = marshal.dumps(data)
    talk_to_server(bs)

inferior_process = None
server_thread = None

def cleanup():
    if inferior_process:
        inferior_process.terminate()
    #if server_thread:
    #    server_thread.terminate()
    logging.shutdown()

def handler(signum, frame):
    cleanup()
    exit(-1)

#signal.signal(signal.SIGINT, handler)
#signal.signal(signal.SIGTERM, handler)
 
def run():
    global inferior_process
    global server_thread
    global server_host
    global server_port
    global timer

    timer = Timer(time_out, send_heart_beat)
    timer.start()

    loop = asyncio.get_event_loop()
    server_thread = Thread(target=start_server, args=(loop,)).start()

    server_host, server_port = cmd_q.get()

    logger.info('server started on {}:{}'.format(server_host, server_port))

    cwd = os.getcwd()
    
    while True:
        try:
            os.chdir(cwd)
            cmd_spec = get_cmd()
            #send_status(cmd_spec)
            if not cmd_spec:
                next
            cmd = cmd_spec['cmd']
            logger.debug('got command '+cmd)
            if cmd == 'terminate':
                break
            if 'dir' in cmd_spec:
                path = cmd_spec['dir']
                try:
                    os.makedirs(path)
                except Exception as e:
                    pass
                os.chdir(path)
            args = shlex.split(cmd)
            out = None
            err = None
            p   = None
            try:
                p = Popen(args, stdout=PIPE, stderr=PIPE)
                inferior_process = p
                out, err = p.communicate()
            except Exception as e:
                err = str(e).encode()
            if 'logfile' in cmd_spec:
                logfile = os.path.abspath(cmd_spec['logfile'])
                logdir = os.path.dirname(logfile)
                if os.path.exists(logfile):
                    rename(logfile, (logfile+'.bak'))
                try:
                    os.makedirs(logdir)
                except Exception as e:
                    pass
                try:
                    fh = open(logfile, 'w')
                    if out:
                        fh.write(out.decode())
                    if err:
                        fh.write(err.decode())
                finally:
                    fh.close()
            if p:
                exitcode = p.returncode
            else:
                exitcode = -1
            if out:
                logger.info("command '{}' passed : {}".format(cmd, out.decode()))
            if err:
                logger.error("command '{}' failed : {}".format(cmd, err.decode()))
            cmd_done(exitcode, err.decode())
        except Exception as e:
            #send_status(str(e))
            logger.error(str(e))
            pass

    cleanup()        
    
def main():

    global host, port, agent_id, out_dir
    
    p = OptionParser()
    p.add_option('-m', '--host', dest='host',
                 help='specify host name')
    p.add_option('-p', '--port', dest='port',
                 help='specify port')
    p.add_option('-i', '--id', dest='id',
                 help='specify id name')
    p.add_option('-o', '--out_dir', dest='out_dir',
                 help='specify output directory')
    p.add_option('-v', '--verbose', dest='verbose', default='1',
                 help='specify verbose level')
    
    (options, args) = p.parse_args()

    host = options.host
    port = int(options.port)
    agent_id = options.id
    out_dir = path.abspath(options.out_dir)

    logger.setLevel(get_level(options.verbose))

    agent_log = path.abspath(path.join(out_dir, 'agents', agent_id))
    try:
        os.makedirs(path.dirname(agent_log))
    except Exception as e:
        pass
    if path.exists(agent_log):
        rename(agent_log, (agent_log+'.bak'))
    fh = logging.FileHandler(agent_log)
    fh.setFormatter(logging.Formatter(FORMAT))
    fh.setLevel(get_level(options.verbose))

    logger.addHandler(fh)

    run()

if __name__ == '__main__':
    main()
