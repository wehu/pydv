from graph import Node, needgraph, actiongraph
from visitor import visitor, join, spawn
from scheduler import Scheduler
from types import GeneratorType
from job import JobEngine
from logger import logger

class EntityBase:
    
    ntts = {}
    
    @classmethod
    def register_entity(cls, name, ntt):
        if name in cls.ntts:
            raise Exception("attempt to redefine an entity " + name)
        else:
            cls.ntts[name] = ntt
            
    def __init__(self, body):
        self.name = body.__name__
        self.body = body
        self.needs = set()
        self.initialized = False
        self.node = Node(self.name)
        self.node.ntt = self
        self.node.color = 'white'
        self.node.waiters = set()
        self.node.waiter_nodes = set()
        self.node.wait_on = set()
        needgraph.add_node(self.node)
        EntityBase.register_entity(self.name, self)
        
    def add_action(self, name, action):
        self.__dict__[name] = action
        return action
    
    def initialize(self):
        if not self.initialized:
            self.initialized = True
            self.body(self)
            
    def __call__(self):
        self.initialize()
        return self

    def __str__(self):
        return self.name

    def need(self, ntt):
        self.needs.add(ntt)
        needgraph.add_edge(self.node, ntt.node)

    def add_waiter(self, n):
        self.node.waiters.add(Scheduler.current)
        self.node.waiter_nodes.add(n)

    def wake_waiters(self):
        for v in self.node.waiters:
            Scheduler.wake(v)

    def build_need(self):
        n = self.node
        if n.color == 'black':
            return
        
        sg = needgraph.subgraph(n)
        for i in self.needs:
            if i.node.color == 'gray':
                i.add_waiter(n)
                n.wait_on.add(i.node)
                sg.remove_node(i.node)
                ssg = needgraph.subgraph(i.node)
                for j in ssg.nodes_iter():
                    sg.remove_node(j)
                    
        for i in sg.nodes_iter():
            if not i.color == 'black':
                i.color = 'gray'

        ns = set()
        def collect_nodes():
            for i in sg.nodes_iter():
                if sg.out_degree(i) == 0 and not i.color == 'black':
                    ns.add(i.ntt)
        collect_nodes()
        while len(ns) > 0:
            @join
            def body(s):
                for i in ns:
                    @spawn(s)
                    def f(ii=i):
                        try:
                            yield from ii.build()
                        finally:
                            ii.node.color = 'black'
                            ns.remove(ii)
                            if sg.has_node(ii.node):
                                sg.remove_node(ii.node)
            yield from body()
            collect_nodes()
            
        while len(n.wait_on) > 0:
            yield from Scheduler.sleep()
            
        for i in n.waiter_nodes:
            i.wait_on.remove(n)
            
        for v in n.waiters:
            Scheduler.wake(v)
            
        n.waiters.clear()
        n.waiter_nodes.clear()

class Entity(EntityBase):
    
    def __init__(self, body):
        super(Entity, self).__init__(body)


def entity(parent=None):
    def f(body):
        ntt = Entity(body)
        return ntt
    return f

def action(parent=None):
    def f(a):
        def na(*args, **kargs):
            fn = a.__name__
            if parent:
                fn = str(parent) + '.' + fn
            logger.info('-> running action {}'.format(fn))
                
            if a.__name__ == 'build':
                if parent:
                    yield from parent.build_need()
            res = a(*args, **kargs)
            if type(res) == GeneratorType:
                res = yield from res
            logger.info('<- action {} finished'.format(fn))
            return res
        if parent:
            parent.add_action(a.__name__, na)
            if a.__name__ == 'build':
                def nna(*args, **kargs):
                    fn = 'build_self'
                    if parent:
                        fn = str(parent) + '.' + fn
                    logger.info('-> running action {}'.format(fn))
                    res = a(*args, **kargs)
                    if type(res) == GeneratorType:
                        res = yield from res
                    logger.info('<- action {} finished'.format(fn))
                    return res
                parent.add_action('build_self', nna)
        return na
    return f

def cmd(*args):
    cmd_spec = {}
    cmd_spec['cmd'] = ' '.join(args)
    v = Scheduler.current
    if v.cwd:
        cmd_spec['dir'] = v.cwd
    JobEngine.push_cmd(v, cmd_spec)
    yield from Scheduler.sleep()
    exitcode = cmd_spec['exitcode']
    if not exitcode == 0:
        errmsg = cmd_spec['errmsg'] + (" with exitcode {}".format(exitcode))
        raise Exception(errmsg)

def dir(p):
    v = Scheduler.current
    v.cwd = p
