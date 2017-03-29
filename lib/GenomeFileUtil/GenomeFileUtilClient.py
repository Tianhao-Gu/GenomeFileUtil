# -*- coding: utf-8 -*-
############################################################
#
# Autogenerated by the KBase type compiler -
# any changes made here will be overwritten
#
############################################################

from __future__ import print_function
# the following is a hack to get the baseclient to import whether we're in a
# package or not. This makes pep8 unhappy hence the annotations.
try:
    # baseclient and this client are in a package
    from .baseclient import BaseClient as _BaseClient  # @UnusedImport
except:
    # no they aren't
    from baseclient import BaseClient as _BaseClient  # @Reimport


class GenomeFileUtil(object):

    def __init__(
            self, url=None, timeout=30 * 60, user_id=None,
            password=None, token=None, ignore_authrc=False,
            trust_all_ssl_certificates=False,
            auth_svc='https://kbase.us/services/authorization/Sessions/Login'):
        if url is None:
            raise ValueError('A url is required')
        self._service_ver = None
        self._client = _BaseClient(
            url, timeout=timeout, user_id=user_id, password=password,
            token=token, ignore_authrc=ignore_authrc,
            trust_all_ssl_certificates=trust_all_ssl_certificates,
            auth_svc=auth_svc)

    def genbank_to_genome(self, params, context=None):
        """
        :param params: instance of type "GenbankToGenomeParams" (genome_name
           - becomes the name of the object workspace_name - the name of the
           workspace it gets saved to. source - Source of the file typically
           something like RefSeq or Ensembl taxon_ws_name - where the
           reference taxons are : ReferenceTaxons taxon_reference - if
           defined, will try to link the Genome to the specified taxonomy
           object insteas of performing the lookup during upload release -
           Release or version number of the data per example Ensembl has
           numbered releases of all their data: Release 31
           generate_ids_if_needed - If field used for feature id is not
           there, generate ids (default behavior is raising an exception)
           genetic_code - Genetic code of organism. Overwrites determined GC
           from taxon object type - Reference, Representative or User upload)
           -> structure: parameter "file" of type "File" -> structure:
           parameter "path" of String, parameter "shock_id" of String,
           parameter "ftp_url" of String, parameter "genome_name" of String,
           parameter "workspace_name" of String, parameter "source" of
           String, parameter "taxon_wsname" of String, parameter
           "taxon_reference" of String, parameter "release" of String,
           parameter "generate_ids_if_needed" of String, parameter
           "genetic_code" of Long, parameter "type" of String, parameter
           "metadata" of type "usermeta" -> mapping from String to String
        :returns: instance of type "GenomeSaveResult" -> structure: parameter
           "genome_ref" of String
        """
        return self._client.call_method(
            'GenomeFileUtil.genbank_to_genome',
            [params], self._service_ver, context)

    def genome_to_gff(self, params, context=None):
        """
        :param params: instance of type "GenomeToGFFParams" (is_gtf -
           optional flag switching export to GTF format (default is 0, which
           means GFF) target_dir - optional target directory to create file
           in (default is temporary folder with name 'gff_<timestamp>'
           created in scratch)) -> structure: parameter "genome_ref" of
           String, parameter "ref_path_to_genome" of list of String,
           parameter "is_gtf" of type "boolean" (A boolean - 0 for false, 1
           for true. @range (0, 1)), parameter "target_dir" of String
        :returns: instance of type "GenomeToGFFResult" (from_cache is 1 if
           the file already exists and was just returned, 0 if the file was
           generated during this call.) -> structure: parameter "gff_file" of
           type "File" -> structure: parameter "path" of String, parameter
           "shock_id" of String, parameter "ftp_url" of String, parameter
           "from_cache" of type "boolean" (A boolean - 0 for false, 1 for
           true. @range (0, 1))
        """
        return self._client.call_method(
            'GenomeFileUtil.genome_to_gff',
            [params], self._service_ver, context)

    def genome_to_genbank(self, params, context=None):
        """
        :param params: instance of type "GenomeToGenbankParams" -> structure:
           parameter "genome_ref" of String, parameter "ref_path_to_genome"
           of list of String
        :returns: instance of type "GenomeToGenbankResult" (from_cache is 1
           if the file already exists and was just returned, 0 if the file
           was generated during this call.) -> structure: parameter
           "genbank_file" of type "File" -> structure: parameter "path" of
           String, parameter "shock_id" of String, parameter "ftp_url" of
           String, parameter "from_cache" of type "boolean" (A boolean - 0
           for false, 1 for true. @range (0, 1))
        """
        return self._client.call_method(
            'GenomeFileUtil.genome_to_genbank',
            [params], self._service_ver, context)

    def export_genome_as_genbank(self, params, context=None):
        """
        :param params: instance of type "ExportParams" (input and output
           structure functions for standard downloaders) -> structure:
           parameter "input_ref" of String
        :returns: instance of type "ExportOutput" -> structure: parameter
           "shock_id" of String
        """
        return self._client.call_method(
            'GenomeFileUtil.export_genome_as_genbank',
            [params], self._service_ver, context)

    def fasta_gff_to_genome(self, params, context=None):
        """
        :param params: instance of type "FastaGFFToGenomeParams" (genome_name
           - becomes the name of the object workspace_name - the name of the
           workspace it gets saved to. source - Source of the file typically
           something like RefSeq or Ensembl taxon_ws_name - where the
           reference taxons are : ReferenceTaxons taxon_reference - if
           defined, will try to link the Genome to the specified taxonomy
           object insteas of performing the lookup during upload release -
           Release or version number of the data per example Ensembl has
           numbered releases of all their data: Release 31 genetic_code -
           Genetic code of organism. Overwrites determined GC from taxon
           object type - Reference, Representative or User upload) ->
           structure: parameter "fasta_file" of type "File" -> structure:
           parameter "path" of String, parameter "shock_id" of String,
           parameter "ftp_url" of String, parameter "gff_file" of type "File"
           -> structure: parameter "path" of String, parameter "shock_id" of
           String, parameter "ftp_url" of String, parameter "genome_name" of
           String, parameter "workspace_name" of String, parameter "source"
           of String, parameter "taxon_wsname" of String, parameter
           "taxon_reference" of String, parameter "release" of String,
           parameter "genetic_code" of Long, parameter "type" of String,
           parameter "scientific_name" of String, parameter "metadata" of
           type "usermeta" -> mapping from String to String
        :returns: instance of type "GenomeSaveResult" -> structure: parameter
           "genome_ref" of String
        """
        return self._client.call_method(
            'GenomeFileUtil.fasta_gff_to_genome',
            [params], self._service_ver, context)

    def status(self, context=None):
        return self._client.call_method('GenomeFileUtil.status',
                                        [], self._service_ver, context)
