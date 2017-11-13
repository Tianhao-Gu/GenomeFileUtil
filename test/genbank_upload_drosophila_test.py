import unittest
import time
import os

from os import environ
try:
    from ConfigParser import ConfigParser  # py2
except:
    from configparser import ConfigParser  # py3

from Workspace.WorkspaceClient import Workspace as workspaceService
from GenomeFileUtil.GenomeFileUtilImpl import GenomeFileUtil
from GenomeFileUtil.GenomeFileUtilServer import MethodContext

from DataFileUtil.DataFileUtilClient import DataFileUtil
from GenomeFileUtil.JsonIOHelper import (download_genome_to_json_files,
                                         compare_genome_json_files)


class GenomeFileUtilTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
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
        cls.wsClient = workspaceService(cls.wsURL, token=token)
        cls.serviceImpl = GenomeFileUtil(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    def getWsClient(self):
        return self.__class__.wsClient

    def getWsName(self):
        if hasattr(self.__class__, 'wsName'):
            return self.__class__.wsName
        suffix = int(time.time() * 1000)
        wsName = "test_GenomeFileUtil_" + str(suffix)
        self.getWsClient().create_workspace({'workspace': wsName})
        self.__class__.wsName = wsName
        return wsName

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    def test_genome_upload_bug(self):
        gbk_path = "data/drosophila/small_test.tar.gz"
        ws_obj_name = 'DrosophilaGenome.1'
        result = self.getImpl().genbank_to_genome(self.getContext(), 
            {
                'file' : { 'path': gbk_path },
                'workspace_name': self.getWsName(),
                'genome_name': ws_obj_name,
                'generate_ids_if_needed': 0
            })[0]
        target_dir = os.path.join("/kb/module/work/tmp", "drosophila")
        download_genome_to_json_files(self.getContext()['token'], result['genome_ref'],
                                      target_dir)
        #self.assertEqual(0, len(compare_genome_json_files(target_dir,
        #                                                  os.path.join("/kb/module/test/data/fungi",
        #                                                               "GCF_000002945"))))
        self.assertTrue(int(result['genome_info'][10]['Number features']) > 0)
        
        res1 = self.getImpl().genome_to_gff(self.getContext(),
            { 'genome_ref': result['genome_ref'] })[0]
