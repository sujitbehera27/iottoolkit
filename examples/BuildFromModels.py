'''
Created on Dec 12, 2013

Create services from a service model instance, create objects from an object model instance 
How are base objects mapped to services? 
This file creates a service object that has multiple services and a single object tree
There could be a service creation service where POSTing this descriptor would 

@author: mjkoster
'''
from interfaces.HttpObjectService import HttpObjectService
from interfaces.CoapObjectService import CoapObjectService

from core.RESTfulResource import RESTfulResource
from core.SmartObject import SmartObject
from core.Description import Description
from core.ObservableProperty import ObservableProperty
from core.Observers import Observers
from core.PropertyOfInterest import PropertyOfInterest
from rdflib.term import Literal, URIRef
from interfaces.HttpObjectService import HttpObjectService
from interfaces.CoapObjectService import CoapObjectService
from time import sleep
import sys
import subprocess
import rdflib
from urlparse import urlparse


#workaround to register rdf JSON plugins 
import rdflib
from rdflib.plugin import Serializer, Parser
rdflib.plugin.register('json-ld', Serializer, 'rdflib_jsonld.serializer', 'JsonLDSerializer')
rdflib.plugin.register('json-ld', Parser, 'rdflib_jsonld.parser', 'JsonLDParser')
rdflib.plugin.register('rdf-json', Serializer, 'rdflib_rdfjson.rdfjson_serializer', 'RdfJsonSerializer')
rdflib.plugin.register('rdf-json', Parser, 'rdflib_rdfjson.rdfjson_parser', 'RdfJsonParser')

'''
model format for populating Description and creating SmartObject instances and service instances
'''
service_metadata = {
    'FQDN': '',
    'IPV4': '',
    'IPV6': ''
    }
#replace with unique service URIs e.g. http://localhost:8000  when starting service instances
services = {
    'localHTTP' : {
        'scheme': 'http',
        'FQDN': 'localhost',
        'port': 8000,
        'IPV4': '',
        'root': '/',
        'discovery': '/'
                    },                
    'localCoAP': {
        'scheme': 'coap',
        'FQDN': 'localhost',
        'port': 5683,
        'IPV4': '',
        'root': '/',
        'discovery': '/' 
                    },
    'localMQTT' : {
        'scheme': 'mqtt',
        'FQDN': 'localhost',
        'port': 1880,
        'IPV4': '',
                    },
             }

object_metadata = {
    'objectPath': '',
    }

objects = {
    '/': {
        'resourceName': '/',
        'resourceClass': 'SmartObject'
        },
    '/services': {
        'resourceName': 'services',
        'resourceClass': 'SmartObject'
        },
    '/sensors': {
        'resourceName': 'sensors',
        'resourceClass': 'SmartObject'
        },
    '/sensors/rhvWeather-01': {
        'resourceName': 'rhvWeather-01',
        'resourceClass': 'SmartObject'
        },
    '/sensors/rhvWeather-01/indoor_temperature': {
        'resourceName': 'indoor_temperature',
        'resourceClass': 'ObservableProperty',
        'resourceType': 'temperature',
        'interfaceType':'sensor',
        'subscriber': ['mqtt://smartobjectservice.com:1883/sensors/rhvWeather-01/indoor_temperature'],
        'publisher': '',
        'bridge': ''
        }
    }


class SystemInstance(object):
    '''
    creates service instances and object instances from dictionary constructors
    {
    'service_metadata': {},
    'services': {},
    'object_metadata': {},
    'objects': {}
    }
    '''
    def __init__(self, systemConstructor):
        
        self._service_metadata = systemConstructor['service_metadata']
        self._services = systemConstructor['services']
        self._object_metadata = systemConstructor['object_metadata']
        self._objects = systemConstructor['objects']
        
        self._baseObject = None
        
        self._defaultResources = {
                                  'SmartObject': ['Description', 'Agent'],
                                  'ObservableProperty': ['Description', 'Observers']
                                  }

        self._observerTypes = ['subscriber', 'publisher', 'bridge']
        
        self._observerSchemes = ['http', 'coap', 'mqtt', 'handler']

        self._mqttObserverTemplate = {
                                      'resourceName': 'mqttObserver',
                                      'resourceClass': 'mqttObserver',
                                      'connection': 'localhost',
                                      'pubTopic': '',
                                      'subTopic': '',
                                      'keepAlive': 60,
                                      'QoS': 0
                                      }
        
        self._httpPublisherTemplate = {
                                       'resourceName': 'httpPublisher',
                                       'resourceClass': 'httpPublisher',
                                       'targetURI': 'http://localhost:8000/'
                                       }
        
        self._httpSubscriberTemplate = {
                                        'resourceName': 'httpSubscriber',
                                        'resourceClass': 'httpSubscriber',
                                        'ObserverURI': 'http://localhost:8000/',
                                        }
        
        self._coapPublisherTemplate = {
                                       'resourceName': 'coapPublisher',
                                       'resourceClass': 'coapPublisher',
                                       'targetURI': 'coap://localhost:5683/'
                                       }
        
        self._coapSubscriberTemplate = {
                                        'resourceName': 'coapSubscriber',
                                        'resourceClass': 'coapSubscriber',
                                        'connection': 'coap://localhost:5683/'
                                        }

        self._callbackNotifierTemplate = {
                                          'resourceName': 'callbackNotifier',
                                          'resourceClass': 'callbackNotifier',
                                          'handlerURI': 'handler://'
                                          }

        '''
        make objects from object models first
        make list sorted by path length for import from graph, 
        could count a split list but this should be the same if we eat slashes somewhere
        '''
        self._resourceList = sorted( self._objects.keys(), key=str.count('/') )
        for self._resource in self._resourceList:
            self._resourceDescriptor = self._objects[self._resource]
            # see if base object needs to be created. 
            if self._resource is '/' and self._resourceDescriptor['resourceClass'] is 'SmartObject' and self._baseObject is None:
                self._baseObject = SmartObject(self._resourceDescriptor)
            else:
                self._newResource = self._objectFromPath(self._resource).create(self._resourceDescriptor)
                
            if self._resourceDescriptor['resourceClass'] in self._defaultResources:
                for self._defaultResource in self._defaultResources[self._resource]:
                    self._newChildResource = self._newResource.create({
                                        'resourceName': self._defaultResource,
                                        'resourceClass': self._defaultResource
                                        })
                    if self._defaultResource is 'Description': 
                        self._newChildResource.create(self._graphFromModel(self._resource, self._resourceDescriptor))
                        # FIXME need to aggregate graphs upstream
            # make observers from the list of URIs of each Observer type
            for self._resourceProperty in self._resourceDescriptor:
                if self._resourceProperty in self._observerTypes:
                    for self._observerURI in self._resourceDescriptor[self._resourceProperty]:
                        self._observerFromURI(self._newResource, self._resourceProperty, self._observerURI )
        '''
        make services
        '''
        # make this a service Object (RESTfulResource) with dict as constructor
        self._serviceRegistry = self._objectFromPath('/services', self._baseObject)
        self._serviceDescription = self._objectFromPath('/services/Description', self._baseObject)        
    
        for self._serviceName in self._services:
            self._newService = ServiceObject(self._serviceName, self._services[self._serviceName], self._serviceRegistry)
            self._serviceRegistry.resources.update({self._serviceName:self._newService})
            self._serviceDescription.set(self._graphFromModel(self._serviceName, self._services[self._serviceName]))
            
    def _graphFromModel(self, link, model):
        # make rdf-json from the model and return RDF graph for loading into Description
        g=rdflib.graph()
        subject=URIRef(link)
        for relation in model:
            value = model[relation]
            g.add(subject, Literal(relation), Literal(value))
        return g

    def _observerFromURI(self, currentResource, observerType, observerURI):
        # split by scheme
        URIObject=urlparse(observerURI)
        # fill in constructor template
        if URIObject.scheme is 'http':
            if observerType is 'publisher':
                resourceConstructor = self._httpPublisherTemplate.copy()
                resourceConstructor['targetURI'] = observerURI
            if observerType is 'subscriber':
                resourceConstructor = self._httpSubscriberTemplate.copy()
                resourceConstructor['observerURI'] = observerURI
    
        if URIObject.scheme is 'coap':
            if observerType is 'publisher':
                resourceConstructor = self._coapPublisherTemplate.copy()
                resourceConstructor['targetURI'] = observerURI
            if observerType is 'subscriber':
                resourceConstructor = self._coapSubscriberTemplate.copy()
                resourceConstructor['observerURI'] = observerURI
    
        if URIObject.scheme is 'mqtt':
            resourceConstructor = self._mqttObserverTemplate.copy() 
            resourceConstructor['connection'] = URIObject.netloc
            if observerType is 'publisher':
                resourceConstructor['pubTopic'] = URIObject.path
            if observerType is 'subscriber':
                resourceConstructor['subTopic'] = URIObject.path
            if observerType is 'bridge':
                resourceConstructor['pubTopic'] = URIObject.path
                resourceConstructor['subTopic'] = URIObject.path

        if URIObject.scheme is 'handler':
            resourceConstructor = self._callbackNotifierTemplate.copy()   
            resourceConstructor['handlerURI'] = observerURI
            
        #create resource in currentResource.resources['Observers'] container  
        currentResource.resources['Observers'].create(resourceConstructor)      

    def _objectFromPath(self, path, baseObject):
    # fails if resource doesn't exist
        currentObject=baseObject
        for pathElement in path.split('/')[:-1]:
            currentObject=object.resources[pathElement]
            return currentObject

class ServiceObject(RESTfulResource):
    def __init__(self, serviceName, serviceConstructor, baseObject):
        resourceConstructor = {
                               'resourceName': serviceName,
                               'resourceClass': serviceConstructor['scheme']
                               }
        RESTfulResource.__init__(self, baseObject, resourceConstructor )
        self._set(serviceConstructor)
                  
        if serviceConstructor['scheme'] is 'http':
            HttpObjectService(self._objectFromPath(serviceConstructor['root'], baseObject), port=serviceConstructor['port'])
            
        if serviceConstructor['scheme'] is 'coap':
            CoapObjectService(self._objectFromPath(serviceConstructor['root'], baseObject), port=serviceConstructor['port'])
                
        if serviceConstructor['scheme'] is 'mqtt':
            subprocess.call('mosquitto -d -p ', serviceConstructor['port'])


if __name__ == '__main__' :
    
    '''
    make an instance using the example constructors
    '''
    systemConstructor = {'service_metadata': service_metadata,
                             'services': services,
                             'object_metadata': object_metadata,
                             'objects': objects
                             }
    
    system = SystemInstance(systemConstructor)
              
    try:
    # register handlers etc.
        while 1: sleep(1)
    except KeyboardInterrupt: pass
    print 'got KeyboardInterrupt'

    