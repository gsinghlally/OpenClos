'''
Created on Jul 22, 2014

@author: moloyc
'''
import os
import sys
sys.path.insert(0,os.path.abspath(os.path.dirname(__file__) + '/' + '../..')) #trick to make it run from CLI

import unittest
import shutil
from flexmock import flexmock
from jnpr.openclos.l3Clos import L3ClosMediation
from jnpr.openclos.model import Pod, Device, InterfaceLogical, InterfaceDefinition, TrapGroup
from test_dao import InMemoryDao 

class TestL3Clos(unittest.TestCase):
    def setUp(self):
        self.__conf = {}
        self.__conf['outputDir'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
        self.__conf['deviceFamily'] = {
            "qfx5100-24q-2p": {
                "ports": 'et-0/0/[0-23]'
            },
            "qfx5100-48s-6q": {
                "uplinkPorts": 'et-0/0/[48-53]', 
                "downlinkPorts": 'xe-0/0/[0-47]'
            },
            "ex4300-24p": {
                "uplinkPorts": 'et-0/1/[0-3]', 
                "downlinkPorts": 'ge-0/0/[0-23]'
            }
        }
        self.__dao = InMemoryDao.getInstance()
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)

    
    def tearDown(self):
        ''' Deletes 'out' folder under test dir'''
        shutil.rmtree(self.__conf['outputDir'], ignore_errors=True)
        InMemoryDao._destroy()
        self.l3ClosMediation = None

    def testLoadClosDefinition(self):
        pods = self.l3ClosMediation.loadClosDefinition()
        self.assertEqual(2, len(pods))

    def testLoadNonExistingClosDefinition(self):
        pods = self.l3ClosMediation.loadClosDefinition('non-existing.yaml')
        self.assertIsNone(pods)
        
        with self.__dao.getReadSession() as session:
            self.assertEqual(0, len(self.__dao.getAll(session, Pod)))

    def getPodDict(self):
        return {"devicePassword": "Embe1mpls", "leafCount": 3, "leafSettings": [{"deviceType":"qfx5100-48s-6q"}], 
                   "spineAS": 100, "spineCount": 2, "spineDeviceType": "qfx5100-24q-2p", "interConnectPrefix": "192.168.0.0/24", 
                   "vlanPrefix": "172.16.0.0/22", "topologyType": "threeStage", "loopbackPrefix": "10.0.0.0/24", "leafAS": 200, 
                   "managementPrefix": "172.32.30.101/24", "hostOrVmCountPerLeaf": 254, "inventory" : "inventoryUnitTest.json"}

    def testCreatePod(self):
        podDict = self.getPodDict()
        self.l3ClosMediation.createPod('pod1', podDict)
        
        with self.__dao.getReadSession() as session:
            self.assertEqual(1, session.query(Pod).count())

    def testUpdatePod(self):
        podDict = self.getPodDict()
        pod = self.l3ClosMediation.createPod('pod1', podDict)

        inventoryDict = {
            "spines" : [
               { "name" : "spine-01", "macAddress" : "10:0e:7e:af:35:41", "deployStatus": "deploy" },
               { "name" : "spine-02", "macAddress" : "10:0e:7e:af:50:c1" }
            ],
            "leafs" : [
               { "name" : "leaf-01", "family" : "qfx5100-48s-6q", "macAddress" : "88:e0:f3:1c:d6:01", "deployStatus": "deploy" },
               { "name" : "leaf-02", "family" : "qfx5100-48s-6q", "macAddress" : "10:0e:7e:b8:9d:01" },
               { "name" : "leaf-03", "family" : "ex4300-24p", "macAddress" : "10:0e:7e:b8:9d:01" }
            ]
        }
        self.l3ClosMediation.updatePod(pod.id, podDict, inventoryDict)

        with self.__dao.getReadSession() as session:
            pod = session.query(Pod).one()
            self.assertEqual(5, len(pod.devices))
            deployCount = 0
            for device in pod.devices:
                if device.deployStatus == "deploy":
                    deployCount += 1
            self.assertEqual(2, deployCount)

    def testUpdatePodInvalidId(self):
        with self.assertRaises(ValueError) as ve:
            self.l3ClosMediation.updatePod("invalid_id", None)

    def createPodSpineLeaf(self):
        podDict = self.getPodDict()
        pod = self.l3ClosMediation.createPod('pod1', podDict)
        return pod
    
    def testCablingPlanAndDeviceConfig(self):
        self.__conf['DOT'] = {'ranksep' : '5 equally', 'colors': ['red', 'green', 'blue']}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        pod = self.createPodSpineLeaf()
        self.assertEqual(True, self.l3ClosMediation.createCablingPlan(pod.id))
        self.assertEqual(True, self.l3ClosMediation.createDeviceConfig(pod.id))

    def testCreateLinks(self):
        pod = self.createPodSpineLeaf()
        
        # force close current session and get new session to make sure merge and flush took place properly
        podId = pod.id

        with self.__dao.getReadSession() as session:
            spine01Port0 = session.query(InterfaceDefinition).join(Device).filter(InterfaceDefinition.name == 'et-0/0/0').filter(Device.name == 'spine-01').filter(Device.pod_id == podId).one()
            self.assertIsNotNone(spine01Port0.peer)
            self.assertEqual('et-0/0/48', spine01Port0.peer.name)
            self.assertEqual('leaf-01', spine01Port0.peer.device.name)
    
            spine02Port0 = session.query(InterfaceDefinition).join(Device).filter(InterfaceDefinition.name == 'et-0/0/0').filter(Device.name == 'spine-02').filter(Device.pod_id == podId).one()
            self.assertIsNotNone(spine02Port0.peer)
            self.assertEqual('et-0/0/49', spine02Port0.peer.name)
            self.assertEqual('leaf-01', spine02Port0.peer.device.name)
    
            spine01Port1 = session.query(InterfaceDefinition).join(Device).filter(InterfaceDefinition.name == 'et-0/0/1').filter(Device.name == 'spine-01').filter(Device.pod_id == podId).one()
            self.assertIsNotNone(spine01Port1.peer)
            self.assertEqual('et-0/0/48', spine01Port1.peer.name)
            self.assertEqual('leaf-02', spine01Port1.peer.device.name)
    
            spine02Port1 = session.query(InterfaceDefinition).join(Device).filter(InterfaceDefinition.name == 'et-0/0/1').filter(Device.name == 'spine-02').filter(Device.pod_id == podId).one()
            self.assertIsNotNone(spine02Port1.peer)
            self.assertEqual('et-0/0/49', spine02Port1.peer.name)
            self.assertEqual('leaf-02', spine02Port1.peer.device.name)
    
            spine01Port2 = session.query(InterfaceDefinition).join(Device).filter(InterfaceDefinition.name == 'et-0/0/2').filter(Device.name == 'spine-01').filter(Device.pod_id == podId).one()
            self.assertIsNotNone(spine01Port2.peer)
            self.assertEqual('uplink-0', spine01Port2.peer.name)
            self.assertEqual('leaf-03', spine01Port2.peer.device.name)
    
            spine02Port2 = session.query(InterfaceDefinition).join(Device).filter(InterfaceDefinition.name == 'et-0/0/2').filter(Device.name == 'spine-02').filter(Device.pod_id == podId).one()
            self.assertIsNotNone(spine02Port2.peer)
            self.assertEqual('uplink-1', spine02Port2.peer.name)
            self.assertEqual('leaf-03', spine02Port2.peer.device.name)

    def testCreateLeafIfds(self):
        with self.__dao.getReadSession() as session:
            from test_model import createPod
            pod = createPod('test', session)
            pod.spineCount = 6
            leaves = [{ "name" : "leaf-01", "family" : "ex4300-24p", "macAddress" : "88:e0:f3:1c:d6:01", "deployStatus": "deploy" }]
    
            self.l3ClosMediation._createLeafIfds(session, pod, leaves)
            interfaces = session.query(InterfaceDefinition).all()
            self.assertEqual(6, len(interfaces))
        
        
    def testGetLeafSpineFromPod(self):
        self.createPodSpineLeaf()
        with self.__dao.getReadSession() as session:
            pod = session.query(Pod).one()
            leafSpineDict = self.l3ClosMediation._getLeafSpineFromPod(pod)
            self.assertEqual(3, len(leafSpineDict['leafs']))
            self.assertEqual(2, len(leafSpineDict['spines']))
        
    def testAllocateLoopback(self):
        pod = self.createPodSpineLeaf()
    
        with self.__dao.getReadSession() as session:
            ifl = session.query(InterfaceLogical).join(Device).filter(InterfaceLogical.name == 'lo0.0').filter(Device.name == 'leaf-01').filter(Device.pod_id == pod.id).one()
            self.assertEqual('10.0.0.1/32', ifl.ipaddress)
            ifl = session.query(InterfaceLogical).join(Device).filter(InterfaceLogical.name == 'lo0.0').filter(Device.name == 'spine-02').filter(Device.pod_id == pod.id).one()
            self.assertEqual('10.0.0.5/32', ifl.ipaddress)
            self.assertEqual('10.0.0.0/29', pod.allocatedLoopbackBlock)

    def testAllocateIrb(self):
        pod = self.createPodSpineLeaf()
        
        with self.__dao.getReadSession() as session:
            ifl = session.query(InterfaceLogical).join(Device).filter(InterfaceLogical.name == 'irb.1').filter(Device.name == 'leaf-01').filter(Device.pod_id == pod.id).one()
            self.assertEqual('172.16.0.1/24', ifl.ipaddress)
            self.assertEqual('172.16.0.0/22', pod.allocatedIrbBlock)

    def testAllocateInterconnect(self):
        pod = self.createPodSpineLeaf()

        with self.__dao.getReadSession() as session:
            ifl = session.query(InterfaceLogical).join(Device).filter(InterfaceLogical.name == 'et-0/0/0.0').filter(Device.name == 'spine-01').filter(Device.pod_id == pod.id).one()
            belowIfd = session.query(InterfaceDefinition).filter(InterfaceDefinition.id == ifl.layer_below_id).one()
            self.assertEqual('et-0/0/0', belowIfd.name)
            self.assertEqual('192.168.0.0/31', ifl.ipaddress)
            ifl = session.query(InterfaceLogical).join(Device).filter(InterfaceLogical.name == 'et-0/0/48.0').filter(Device.name == 'leaf-01').filter(Device.pod_id == pod.id).one()
            belowIfd = session.query(InterfaceDefinition).filter(InterfaceDefinition.id == ifl.layer_below_id).one()
            self.assertEqual('et-0/0/48', belowIfd.name)
            self.assertEqual('192.168.0.1/31', ifl.ipaddress)

    def testAllocateAsNumber(self):
        self.createPodSpineLeaf()

        with self.__dao.getReadSession() as session:
            self.assertEqual(100, session.query(Device).filter(Device.role == 'spine').all()[0].asn)
            self.assertEqual(201, session.query(Device).filter(Device.role == 'leaf').all()[1].asn)
        
    def testCreatePolicyOptionSpine(self):
        self.createPodSpineLeaf()
        with self.__dao.getReadSession() as session:
            pod = session.query(Pod).one()
            device = Device("test", "qfx5100-24q-2p", "user", "pwd", "spine", "mac", "mgmtIp", pod)
            device.pod.allocatedIrbBlock = '10.0.0.0/28'
            device.pod.allocatedLoopbackBlock = '11.0.0.0/28'
            configlet = self.l3ClosMediation._createPolicyOption(session, device)
        
        self.assertTrue('irb_in' not in configlet and '10.0.0.0/28' in configlet)
        self.assertTrue('lo0_in' not in configlet and '11.0.0.0/28' in configlet)
        self.assertTrue('lo0_out' not in configlet)
        self.assertTrue('irb_out' not in configlet)

    def testCreatePolicyOptionLeaf(self):
        self.createPodSpineLeaf()
        with self.__dao.getReadSession() as session:
            pod = session.query(Pod).one()
            device = Device("test", "qfx5100-48s-6q", "user", "pwd", "leaf", "mac", "mgmtIp", pod)
            device.pod.allocatedIrbBlock = '10.0.0.0/28'
            device.pod.allocatedLoopbackBlock = '11.0.0.0/28'        
            mockSession = flexmock(session)
            mockSession.should_receive('query.join.filter.filter.one').and_return(InterfaceLogical("test", device, '12.0.0.0/28'))
    
            configlet = self.l3ClosMediation._createPolicyOption(session, device)
            self.assertTrue('irb_in' not in configlet and '10.0.0.0/28' in configlet)
            self.assertTrue('lo0_in' not in configlet and '11.0.0.0/28' in configlet)
            self.assertTrue('lo0_out' not in configlet and '12.0.0.0/28' in configlet)
            self.assertTrue('irb_out' not in configlet)
  
    def testInitWithTemplate(self):
        from jinja2 import TemplateNotFound

        self.assertIsNotNone(self.l3ClosMediation._templateEnv.get_template('protocolBgp.txt'))
        with self.assertRaises(TemplateNotFound) as e:
            self.l3ClosMediation._templateEnv.get_template('unknown-template')
        self.assertTrue('unknown-template' in e.exception.message)

    def createTrapGroupsInDb(self, dao):
        newtargets = []
        for newtarget in ['1.2.3.4', '1.2.3.5']:
            newtargets.append ( TrapGroup ( 'networkdirector_trap_group', newtarget, int('10162') ) )
            newtargets.append ( TrapGroup ( 'openclos_trap_group', newtarget, 20162 ) )
        with self.__dao.getReadWriteSession() as session:
            self.__dao.createObjects(session, newtargets)

    def testGetNdTrapGroupSettingsNoNd(self):
        with self.__dao.getReadSession() as session:
            self.assertEqual(0, len(self.l3ClosMediation._getNdTrapGroupSettings(session)))
        
    def testGetNdTrapGroupSettingsWithNd(self):
        self.__conf['deploymentMode'] = {'ndIntegrated': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        with self.__dao.getReadSession() as session:
            self.assertEqual(0, len(self.l3ClosMediation._getNdTrapGroupSettings(session)))
        
        self.createTrapGroupsInDb(self.__dao)
        with self.__dao.getReadSession() as session:
            self.assertEqual(1, len(self.l3ClosMediation._getNdTrapGroupSettings(session)))
            self.assertEqual(10162, self.l3ClosMediation._getNdTrapGroupSettings(session)[0]['port'])
            self.assertEqual(2, len(self.l3ClosMediation._getNdTrapGroupSettings(session)[0]['targetIp']))
        
    def testGetOpenClosTrapGroupSettingsNoStagedZtp(self):
        with self.__dao.getReadSession() as session:
            self.assertEqual(0, len(self.l3ClosMediation._getOpenclosTrapGroupSettings(session)))
        
    def testGetOpenClosTrapGroupSettingsWithStagedZtp(self):
        self.__conf['deploymentMode'] = {'ztpStaged': True}
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '1.2.3.4'}}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        with self.__dao.getReadSession() as session:
            self.assertEqual(1, len(self.l3ClosMediation._getOpenclosTrapGroupSettings(session)))
            self.assertEqual(1, len(self.l3ClosMediation._getOpenclosTrapGroupSettings(session)[0]['targetIp']))
            self.assertEqual('1.2.3.4', self.l3ClosMediation._getOpenclosTrapGroupSettings(session)[0]['targetIp'][0])
        
        self.createTrapGroupsInDb(self.__dao)
        with self.__dao.getReadSession() as session:
            self.assertEqual(1, len(self.l3ClosMediation._getOpenclosTrapGroupSettings(session)))
            self.assertEqual(20162, self.l3ClosMediation._getOpenclosTrapGroupSettings(session)[0]['port'])
            self.assertEqual(2, len(self.l3ClosMediation._getOpenclosTrapGroupSettings(session)[0]['targetIp']))

    def testCreateSnmpTrapAndEventNoNdSpine(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '1.2.3.4'}}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)
        
        device = Device("test", "qfx5100-48s-6q", "user", "pwd", "spine", "mac", "mgmtIp", None)
        with self.__dao.getReadSession() as session:
            configlet = self.l3ClosMediation._createSnmpTrapAndEvent(session, device)

        self.assertEqual('', configlet)
  
    def testCreateSnmpTrapAndEventNoNdLeafNoStagedZtp(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '1.2.3.4'}}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)
        
        device = Device("test", "qfx5100-48s-6q", "user", "pwd", "leaf", "mac", "mgmtIp", None)
        with self.__dao.getReadSession() as session:
            configlet = self.l3ClosMediation._createSnmpTrapAndEvent(session, device)
        
        self.assertEqual('', configlet)
        
    def testCreateSnmpTrapAndEventNoNdLeafWithStagedZtp(self):
        self.__conf['deploymentMode'] = {'ztpStaged': True}
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '1.2.3.4'}}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)
        
        device = Device("test", "qfx5100-48s-6q", "user", "pwd", "leaf", "mac", "mgmtIp", None)
        with self.__dao.getReadSession() as session:
            configlet = self.l3ClosMediation._createSnmpTrapAndEvent(session, device)
        
        self.assertTrue('' != configlet)
        self.assertTrue('event-options' in configlet)
        self.assertTrue('trap-group openclos_trap_group' in configlet)
        self.assertFalse('trap-group networkdirector_trap_group' in configlet)

    def testCreateSnmpTrapAndEventWithNdSpine(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '5.6.7.8'}}
        self.__conf['deploymentMode'] = {'ndIntegrated': True, 'ztpStaged': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)
        
        device = Device("test", "qfx5100-48s-6q", "user", "pwd", "spine", "mac", "mgmtIp", None)
        with self.__dao.getReadSession() as session:
            configlet = self.l3ClosMediation._createSnmpTrapAndEvent(session, device)

        self.assertTrue('' != configlet)
        self.assertTrue('event-options' in configlet)
        self.assertFalse('trap-group openclos_trap_group' in configlet)
        self.assertTrue('trap-group networkdirector_trap_group' in configlet)

    def testCreateSnmpTrapAndEventWithNdLeaf(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '5.6.7.8'}}
        self.__conf['deploymentMode'] = {'ndIntegrated': True, 'ztpStaged': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)
        
        device = Device("test", "qfx5100-48s-6q", "user", "pwd", "leaf", "mac", "mgmtIp", None)
        with self.__dao.getReadSession() as session:
            configlet = self.l3ClosMediation._createSnmpTrapAndEvent(session, device)

        self.assertTrue('' != configlet)
        #print configlet
        self.assertTrue('event-options' in configlet)
        self.assertTrue('trap-group openclos_trap_group' in configlet)
        self.assertTrue('trap-group networkdirector_trap_group' in configlet)

    def testCreateSnmpTrapAndEventForLeafFor2ndStage(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '5.6.7.8'}}
        self.__conf['deploymentMode'] = {'ndIntegrated': True, 'ztpStaged': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)
        
        device = Device("test", "qfx5100-48s-6q", "user", "pwd", "leaf", "mac", "mgmtIp", None)
        with self.__dao.getReadSession() as session:
            configlet = self.l3ClosMediation._createSnmpTrapAndEventForLeafFor2ndStage(session, device)
        self.assertTrue('' != configlet)
        self.assertTrue('event-options' in configlet)
        self.assertTrue('trap-group openclos_trap_group' in configlet) # this is for delete snmp trap
        self.assertTrue('trap-group networkdirector_trap_group' in configlet)
        self.assertEquals(1, configlet.count('authentication'))
        self.assertEquals(1, configlet.count('link'))
                
    def testCreateRoutingOptionsStatic(self):
        self.createPodSpineLeaf()
        with self.__dao.getReadSession() as session:
            pod = session.query(Pod).one()
            device = Device("test", "qfx5100-48s-6q", "user", "pwd", "leaf", "mac", "mgmtIp", pod)
            device.pod.outOfBandGateway = '10.0.0.254'
            device.pod.outOfBandAddressList = '10.0.10.5/32, 10.0.20.5/32'
    
            configlet = self.l3ClosMediation._createRoutingOptionsStatic(session, device)
            self.assertEquals(1, configlet.count('static'))
            self.assertEquals(2, configlet.count('route'))

    def testCreateAccessInterfaceNoNd(self):
        configlet = self.l3ClosMediation._createAccessPortInterfaces('qfx5100-48s-6q')
        self.assertEquals(48, configlet.count('family ethernet-switching'))
        self.assertTrue('xe-0/0/0' in configlet)
        self.assertTrue('xe-0/0/47' in configlet)

    def testCreateAccessInterfaceEx4300NoNd(self):
        self.__conf['deviceFamily']['ex4300-48p'] = {
                "uplinkPorts": 'et-0/0/[48-51]', 
                "downlinkPorts": 'ge-0/0/[0-47]'
        }
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        configlet = self.l3ClosMediation._createAccessPortInterfaces('ex4300-48p')
        self.assertEquals(48, configlet.count('family ethernet-switching'))
        self.assertTrue('ge-0/0/0' in configlet)
        self.assertTrue('ge-0/0/47' in configlet)

    def testCreateAccessInterfaceNd(self):
        self.__conf['deploymentMode'] = {'ndIntegrated': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        configlet = self.l3ClosMediation._createAccessPortInterfaces('qfx5100-48s-6q')
        self.assertEquals(48, configlet.count('family ethernet-switching'))

    def testCreateLeafGenericConfigNoNd(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '5.6.7.8'}}
        self.__conf['deviceFamily']['ex4300-24p'] = {"uplinkPorts": 'et-0/1/[0-3]', "downlinkPorts": 'ge-0/0/[0-23]'}
        self.__conf['deploymentMode'] = {'ztpStaged': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        
        self.createPodSpineLeaf()
        with self.__dao.getReadSession() as session:
            pod = session.query(Pod).one()
            pod.outOfBandGateway = '10.0.0.254'
            pod.outOfBandAddressList = '10.0.10.5/32'
            
            leafSettings = self.l3ClosMediation._createLeafGenericConfigsFor2Stage(session, pod)
            self.assertTrue(1, len(leafSettings))
            configlet = leafSettings[0].config

        self.assertTrue('' != configlet)
        #print configlet
        self.assertTrue('trap-group openclos_trap_group' in configlet)
        self.assertEquals(1, configlet.count('static'))
        self.assertEquals(2, configlet.count('route'))

    def testCreateLeafGenericConfigWithNd(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '5.6.7.8'}}
        self.__conf['deviceFamily']['ex4300-24p'] = {"uplinkPorts": 'et-0/1/[0-3]', "downlinkPorts": 'ge-0/0/[0-23]'}
        self.__conf['deploymentMode'] = {'ndIntegrated': True, 'ztpStaged': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)


        self.createPodSpineLeaf()
        with self.__dao.getReadSession() as session:
            pod = session.query(Pod).one()
            pod.outOfBandGateway = '10.0.0.254'
            pod.outOfBandAddressList = '10.0.10.5/32, 10.0.10.6'
            
            leafSettings = self.l3ClosMediation._createLeafGenericConfigsFor2Stage(session, pod)
            self.assertTrue(1, len(leafSettings))
            configlet = leafSettings[0].config

        self.assertTrue('' != configlet)
        #print configlet
        self.assertTrue('vendor-id Juniper-qfx5100-48s-6q' in configlet)
        self.assertTrue('trap-group openclos_trap_group' in configlet)
        self.assertTrue('trap-group networkdirector_trap_group' in configlet)
        self.assertEquals(1, configlet.count('static'))
        self.assertEquals(4, configlet.count('route'))

    def testGetSnmpTrapTargets(self):
        with self.__dao.getReadSession() as session:
            self.assertEqual(0, len(self.l3ClosMediation._getSnmpTrapTargets(session)))

    def testGetSnmpTrapTargetsNoNdWithStagedZtp(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '5.6.7.8'}}
        self.__conf['deploymentMode'] = {'ztpStaged': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)

        with self.__dao.getReadSession() as session:
            self.assertEqual(1, len(self.l3ClosMediation._getSnmpTrapTargets(session)))
            self.assertEqual('5.6.7.8', self.l3ClosMediation._getSnmpTrapTargets(session)[0])

    def testGetSnmpTrapTargetsWithNd(self):
        self.__conf['snmpTrap'] = {'openclos_trap_group': {'port': 20162, 'target': '5.6.7.8'}}
        self.__conf['deploymentMode'] = {'ndIntegrated': True, 'ztpStaged': True}
        self.l3ClosMediation = L3ClosMediation(self.__conf, InMemoryDao)
        self.createTrapGroupsInDb(self.__dao)

        with self.__dao.getReadSession() as session:
            self.assertEqual(4, len(self.l3ClosMediation._getSnmpTrapTargets(session)))
            self.assertTrue('5.6.7.8' not in self.l3ClosMediation._getSnmpTrapTargets(session))

if __name__ == '__main__':
    unittest.main()