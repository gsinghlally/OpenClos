import os
import argparse
import fileinput
import re

import util
from crypt import Cryptic
from model import TrapGroup
from dao import Dao

#------------------------------------------------------------------------------
#------------------------------------------------------------------------------

parser = argparse.ArgumentParser ()
parser.add_argument ( '--ndvip',
                      action = 'store',
                      help   = 'VIP address used by Network Director' )
parser.add_argument ( '--nodeip',
                      action = 'store',
                      help   = 'Node IP address for Network Director' )
parser.add_argument ( '--restport',
                      action = 'store',
                      help   = 'Port number to which REST server will bind' )
parser.add_argument ( '--traptgt',
                      action = 'append',
                      help   = 'IP Network Director uses to receive trap' )
parser.add_argument ( '--dbuser',
                      action = 'store',
                      help   = 'User Name to access DB' )
parser.add_argument ( '--dbpass',
                      action = 'store',
                      help   = 'Password to access DB' )
parser.add_argument ( '--ndtrapport',
                      action = 'store',
                      help   = 'Port number Network Director uses to receive trap' )

#------------------------------------------------------------------------------
#------------------------------------------------------------------------------

class NDConfMgr:

    def __init__ ( self, parser ):
        self.cmd_args = parser.parse_args ()
        self.check_stale_entry = 0

#------------------------------------------------------------------------------
    def do_sanity_check ( self ):
        error_str = ""
        if ( self.cmd_args.ndvip == None ):
            error_str += "- Network Director VIP address (--ndvip) not provided\n"

        if ( self.cmd_args.nodeip == None ):
            error_str += "- Node IP address (--nodeip) not provided\n"

        if ( self.cmd_args.restport == None ):
            error_str += "- REST Port number (--restport) not provided\n"

        if ( self.cmd_args.traptgt == None ):
            error_str += "- Trap Target address(es) (--traptgt) not provided\n"

        if ( self.cmd_args.dbuser == None ):
            error_str += "- DB User name (--dbuser) not provided\n"

        if ( self.cmd_args.dbpass == None ):
            error_str += "- DB Password (--dbpass) not provided\n"

        if ( self.cmd_args.ndtrapport == None ):
            error_str += "- Network Director Trap Port number (--ndtrapport) not provided\n"

        if len ( error_str ) is 0:
            ip_format = re.compile ( "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$" )

            if ip_format.match ( self.cmd_args.ndvip ) is None:
                error_str += "- Network Director VIP address is not valid\n"

            if ip_format.match ( self.cmd_args.nodeip ) is None:
                error_str += "- Node IP address is not valid\n"

            for ip_address in ( self.cmd_args.traptgt ):
                if ip_format.match ( ip_address ) is None:
                    error_str += "- Trap Target address " + ip_address + " is not valid\n"
        else:
            error_str += "\nPlease use -h option to view all command arguments"

        return error_str

#------------------------------------------------------------------------------
    def process_line ( self, line ):
        
        if 'twoStageConfigurationCallback:' in line:
            return "twoStageConfigurationCallback: '/sbin/ip a list dev eth0 | grep -q eth0:0'\n"
            
        if '    ndIntegrated :' in line:
            return '    ndIntegrated : true\n'

        if '    ztpStaged :' in line:
            return '    ztpStaged : true\n'

        if 'dbUrl :' in line:
            return '#' + line

        if re.search ( 'dbDialect', line ) is not None:
            return 'dbDialect : mysql\n'

        if re.search ( 'dbHost', line ) is not None:
            return 'dbHost : ' + self.cmd_args.ndvip + '\n'

        if re.search ( 'dbUser', line ) is not None:
            return 'dbUser : ' + "'" + self.cmd_args.dbuser + "'" + '\n'

        if re.search ( 'dbPassword', line) is not None:
            return 'dbPassword : ' + "'" + self.db_pass_crypt + "'" + '\n'

        if re.search ( 'dbName', line ) is not None:
            return 'dbName : openclos\n'

        if self.get_stale_entry_flag () is 1:
            if '            - ' in line:
                return None
            else:
                self.set_stale_entry_flag ()

        return line

#------------------------------------------------------------------------------
    def set_stale_entry_flag ( self ):
        self.check_stale_entry = 1

#------------------------------------------------------------------------------
    def get_stale_entry_flag ( self ):
        return self.check_stale_entry
#------------------------------------------------------------------------------
    def do_configuration ( self ):
        is_input_valid = self.do_sanity_check ()
        if len ( is_input_valid ) is not 0:
            print "\nAborting OpenCLOS configuration due to following errors:\n"
            print is_input_valid
            return None

        print "Configuring OpenCLOS with following parameters:"
        print "ND VIP         : " + self.cmd_args.ndvip
        print "ND node IP     : " + self.cmd_args.nodeip
        print "REST Port      : " + self.cmd_args.restport
        print "DB User        : " + self.cmd_args.dbuser
        self.db_pass_crypt = Cryptic ().encrypt ( self.cmd_args.dbpass )
        print "DB Pass        : " + self.db_pass_crypt
        print "ND Trap Port   : " + self.cmd_args.ndtrapport
        print "Trap Target(s) : "
        for ip_address in self.cmd_args.traptgt:
            print "                 - " + ip_address
            

        conf_file = os.path.join ( util.configLocation,
                                   'openclos.yaml' )
        try:
            lineIter = fileinput.input ( conf_file, inplace=True )
            for line in lineIter:
                if 'httpServer :' in line:
                    print line,
                    print lineIter.next(),
                    print '    port : ' + self.cmd_args.restport
                    lineIter.next (),
                elif '    openclos_trap_group :' in line:
                    print line,
                    print '        port : ' + str(20162)
                    lineIter.next (),
                    print '        target : ' + self.cmd_args.nodeip
                    lineIter.next (),
                else:
                    add_line = self.process_line ( line )
                    if add_line is not None:
                        print add_line,
            return "success"
            
        except ( OSError,IOError ) as e:
            print "Could not open " + conf_file
            print e
            return None

#------------------------------------------------------------------------------
    def update_trap_data_in_DB ( self ):
        util.loadConfig()
        dao = Dao.getInstance()
        with dao.getReadWriteSession() as session:
            trapGroups = dao.getAll(session, TrapGroup)
            if trapGroups:
                dao.deleteObjects (session, trapGroups)

            newtargets = []
            for newtarget in self.cmd_args.traptgt:
                newtargets.append ( TrapGroup ( 'networkdirector_trap_group', newtarget, int(self.cmd_args.ndtrapport) ) )
                newtargets.append ( TrapGroup ( 'openclos_trap_group', newtarget, 20162 ) )
            dao.createObjects(session, newtargets)

#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
if __name__ == "__main__":
    conf_mgr = NDConfMgr ( parser )
    if conf_mgr.do_configuration () is not None:
        conf_mgr.update_trap_data_in_DB ()
