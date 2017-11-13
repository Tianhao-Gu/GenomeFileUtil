import unittest
import os
import json
import time
import shutil
import urllib2
from contextlib import closing

from os import environ
try:
    from ConfigParser import ConfigParser  # py2
except:
    from configparser import ConfigParser  # py3

from pprint import pprint

from Workspace.WorkspaceClient import Workspace as workspaceService
from GenomeFileUtil.GenomeFileUtilImpl import GenomeFileUtil
from GenomeFileUtil.GenomeFileUtilServer import MethodContext

from DataFileUtil.DataFileUtilClient import DataFileUtil

from GenomeFileUtil.JsonIOHelper import (download_genome_to_json_files,
                                         compare_genome_json_files)


class MinimalGenbankUploadTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print('setting up class')
        token = environ.get('KB_AUTH_TOKEN', None)
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': token,
                        'provenance': [
                            {'service': 'GenomeFileUtil',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        config_file = environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('GenomeFileUtil'):
            cls.cfg[nameval[0]] = nameval[1]
        cls.wsURL = cls.cfg['workspace-url']

        cls.ws = workspaceService(cls.wsURL, token=token)
        cls.impl = GenomeFileUtil(cls.cfg)

        cls.MINIMAL_TEST_FILE = os.path.join( cls.cfg['scratch'], 'minimal.gbff')
        shutil.copy('data/minimal.gbff', cls.MINIMAL_TEST_FILE )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.ws.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    def getWsClient(self):
        return self.ws

    def getWsName(self):
        if hasattr(self.__class__, 'wsName'):
            return self.__class__.wsName
        suffix = int(time.time() * 1000)
        wsName = "test_GenomeFileUtil_" + str(suffix)
        ret = self.getWsClient().create_workspace({'workspace': wsName})
        self.__class__.wsName = wsName
        return wsName

    def getImpl(self):
        return self.__class__.impl

    def getContext(self):
        return self.__class__.ctx

    def test_upload(self):

        # fetch the test files and set things up
        genomeFileUtil = self.getImpl()
        gbk_path = self.MINIMAL_TEST_FILE

        # ok, first test with minimal options
        result = genomeFileUtil.genbank_to_genome(self.getContext(),
                                    {
                                        'file':{'path': gbk_path},
                                        'workspace_name': self.getWsName(),
                                        'genome_name': 'something',
                                    })[0]
        self.check_minimal_items_exist(result)

        # test without using ontologies, and with setting a taxon_reference directly
        result = genomeFileUtil.genbank_to_genome(self.getContext(),
                                    {
                                        'file':{'path': gbk_path},
                                        'workspace_name': self.getWsName(),
                                        'genome_name': 'something',
                                        'exclude_ontologies':1,
                                        'taxon_reference':'ReferenceTaxons/4932_taxon'
                                    })[0]
        self.check_minimal_items_exist(result)

        # test setting additional metadata
        result = genomeFileUtil.genbank_to_genome(self.getContext(),
                                    {
                                        'file':{'path': gbk_path},
                                        'workspace_name': self.getWsName(),
                                        'genome_name': 'something',
                                        'exclude_ontologies':1,
                                        'taxon_reference':'ReferenceTaxons/4932_taxon',
                                        'metadata': { 'mydata' : 'yay', 'otherdata':'ok' }
                                    })[0]
        self.check_minimal_items_exist(result)
        metadata_saved = result['genome_info'][10]
        self.assertTrue('mydata' in metadata_saved)
        self.assertTrue('otherdata' in metadata_saved)
        self.assertEquals(metadata_saved['mydata'], 'yay')
        target_dir = os.path.join("/kb/module/work/tmp", "minimal")
        download_genome_to_json_files(self.getContext()['token'], result['genome_ref'],
                                      target_dir)
        #self.assertEqual(0, len(compare_genome_json_files(target_dir, 
        #                                                  os.path.join("/kb/module/test/data", 
        #                                                               "minimal"))))





    def check_minimal_items_exist(self, result):

        self.assertTrue('genome_info' in result)
        self.assertTrue('genome_ref' in result)
        self.assertTrue('report_name' in result)
        self.assertTrue('report_ref' in result)

        genome_info = result['genome_info']
        self.assertEquals(genome_info[10]['Number contigs'],'1')
        self.assertEquals(genome_info[10]['Number features'],'2')
        self.assertEquals(genome_info[10]['Domain'],'Eukaryota')
        self.assertEquals(genome_info[10]['Genetic code'],'11')
        self.assertEquals(genome_info[10]['Name'],'Saccharomyces cerevisiae')
        self.assertEquals(genome_info[10]['Source'], 'Genbank')
        self.assertEquals(genome_info[10]['GC content'], '0.37967')
        self.assertEquals(genome_info[10]['Size'], '5028')
        self.assertEquals(genome_info[10]['Taxonomy'],
            'cellular organisms; Eukaryota; Opisthokonta; Fungi; Dikarya; Ascomycota; '+
            'saccharomyceta; Saccharomycotina; Saccharomycetes; Saccharomycetales; '+
            'Saccharomycetaceae; Saccharomyces')


