from visitor import visitor
from entity import entity, action, cmd
from utils import require
from os import environ
from logger import logger
import event
from namespace import component, suite

if 'DVPY_PRELOAD' in environ:
    for f  in environ['DVPY_PRELOAD'].split(':'):
        logger.info('loading file '+f+'.py')
        require(f)
