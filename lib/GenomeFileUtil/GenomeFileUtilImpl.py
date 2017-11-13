# -*- coding: utf-8 -*-
#BEGIN_HEADER

import os
import shutil
import json
from pprint import pprint

from GenomeFileUtil.core.GenbankToGenome import GenbankToGenome
from GenomeFileUtil.core.GenomeToGFF import GenomeToGFF
from GenomeFileUtil.core.GenomeToGenbank import GenomeToGenbank
from GenomeFileUtil.core.FastaGFFToGenome import FastaGFFToGenome
from GenomeFileUtil.core.GenomeInterface import GenomeInterface

from Workspace.WorkspaceClient import Workspace
from DataFileUtil.DataFileUtilClient import DataFileUtil

# Used to store and pass around configuration URLs more easily
class SDKConfig:
    def __init__(self, config):
        self.workspaceURL = config['workspace-url']
        self.shockURL = config['shock-url']
        self.handleURL = config['handle-service-url']
        self.callbackURL = os.environ['SDK_CALLBACK_URL']
        self.sharedFolder = config['scratch']
        self.srvWizURL = config['srv-wiz-url']
        self.token = os.environ['KB_AUTH_TOKEN']
        self.authServiceUrl = config['auth-service-url']
        self.raw = config

#END_HEADER


class GenomeFileUtil:
    '''
    Module Name:
    GenomeFileUtil

    Module Description:
    
    '''

    ######## WARNING FOR GEVENT USERS ####### noqa
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    ######################################### noqa
    VERSION = "0.6.9"
    GIT_URL = "https://github.com/Tianhao-Gu/GenomeFileUtil.git"
    GIT_COMMIT_HASH = "1661ded3a84156a0b980eccc44bcb9892c425e85"

    #BEGIN_CLASS_HEADER
    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.cfg = SDKConfig(config)
        #END_CONSTRUCTOR
        pass


    def genbank_to_genome(self, ctx, params):
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
        # ctx is the context object
        # return variables are: result
        #BEGIN genbank_to_genome
        print('genbank_to_genome -- paramaters = ')
        pprint(params)

        importer = GenbankToGenome(self.cfg)
        result = importer.refactored_import(ctx, params)

        print('import complete -- result = ')
        pprint(result)
        #END genbank_to_genome

        # At some point might do deeper type checking...
        if not isinstance(result, dict):
            raise ValueError('Method genbank_to_genome return value ' +
                             'result is not type dict as required.')
        # return the results
        return [result]

    def genome_to_gff(self, ctx, params):
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
        # ctx is the context object
        # return variables are: result
        #BEGIN genome_to_gff
        print('genome_to_gff -- paramaters = ')
        pprint(params)

        exporter = GenomeToGFF(self.cfg)
        result = exporter.export(ctx, params)

        print('export complete -- result = ')
        pprint(result)
        #END genome_to_gff

        # At some point might do deeper type checking...
        if not isinstance(result, dict):
            raise ValueError('Method genome_to_gff return value ' +
                             'result is not type dict as required.')
        # return the results
        return [result]

    def genome_to_genbank(self, ctx, params):
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
        # ctx is the context object
        # return variables are: result
        #BEGIN genome_to_genbank
        print('genome_to_genbank -- paramaters = ')
        pprint(params)

        exporter = GenomeToGenbank(self.cfg)
        result = exporter.export(ctx, params)

        print('export complete -- result = ')
        pprint(result)
        #END genome_to_genbank

        # At some point might do deeper type checking...
        if not isinstance(result, dict):
            raise ValueError('Method genome_to_genbank return value ' +
                             'result is not type dict as required.')
        # return the results
        return [result]

    def export_genome_as_genbank(self, ctx, params):
        """
        :param params: instance of type "ExportParams" (input and output
           structure functions for standard downloaders) -> structure:
           parameter "input_ref" of String
        :returns: instance of type "ExportOutput" -> structure: parameter
           "shock_id" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN export_genome_as_genbank
        print('export_genome_as_genbank -- paramaters = ')

        # validate parameters
        if 'input_ref' not in params:
            raise ValueError('Cannot run export_genome_as_genbank- no "input_ref" field defined.')

        # get WS metadata to get ws_name and obj_name
        ws = Workspace(url=self.cfg.workspaceURL)
        info = ws.get_object_info_new({'objects':[{'ref': params['input_ref'] }],'includeMetadata':0, 'ignoreErrors':0})[0]

        genome_to_genbank_params = {
            'genome_ref': params['input_ref']
        }

        # export to file (building from KBase Genome Object)
        result = self.genome_to_genbank(ctx, genome_to_genbank_params)[0]['genbank_file'];

        # create the output directory and move the file there
        export_package_dir = os.path.join(self.cfg.sharedFolder, info[1])
        os.makedirs(export_package_dir)
        shutil.move(
          result['file_path'],
          os.path.join(export_package_dir, os.path.basename(result['file_path'])))

        # export original uploaded GenBank file if it existed.
        exporter = GenomeToGenbank(self.cfg)
        original_result_full = exporter.export_original_genbank(ctx, genome_to_genbank_params)
        if original_result_full is not None:
            original_result = original_result_full['genbank_file']
            shutil.move(
              original_result['file_path'],
              os.path.join(export_package_dir, os.path.basename(original_result['file_path'])))

        # Make warning file about genes only.
        warning_filename = "warning.txt"
        with open(os.path.join(export_package_dir, warning_filename), 'wb') as temp_file:
            temp_file.write('Please note: the KBase-derived GenBank file for annotated genome ' +
                            'objects currently only shows "gene" features. CDS and mRNA ' +
                            'feature types are not currently included in the GenBank download, ' +
                            'but are in the KBase Genome object. ' +
                            'We hope to address this issue in the future.\n\n' +
                            'This directory includes the KBase-derived GenBank file and also ' +
                            '(if you originally uploaded the genome from an annotated ' +
                            'GenBank file) the original GenBank input.')

        # package it up and be done
        dfUtil = DataFileUtil(self.cfg.callbackURL)
        package_details = dfUtil.package_for_download({
                                    'file_path': export_package_dir,
                                    'ws_refs': [ params['input_ref'] ]
                                })

        output = { 'shock_id': package_details['shock_id'] }

        print('export complete -- result = ')
        pprint(output)
        #END export_genome_as_genbank

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method export_genome_as_genbank return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]

    def fasta_gff_to_genome(self, ctx, params):
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
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN fasta_gff_to_genome
        print '--->\nRunning GenomeFileUtil.fasta_gff_to_genome\nparams:'
        print json.dumps(params, indent=1)

        for key in params.keys():
            if params[key] is None:
                del params[key]

        for key, value in params.iteritems():
            if isinstance(value, basestring):
                params[key] = value.strip()

        importer = FastaGFFToGenome(self.cfg)
        returnVal = importer.import_file(params)
        #END fasta_gff_to_genome

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method fasta_gff_to_genome return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]

    def save_one_genome(self, ctx, params):
        """
        :param params: instance of type "SaveOneGenomeParams" -> structure:
           parameter "workspace" of String, parameter "name" of String,
           parameter "data" of type "Genome" (Genome object holds much of the
           data relevant for a genome in KBase Genome publications should be
           papers about the genome, not papers about certain features of the
           genome (which go into the Feature object) Should the Genome object
           have a list of feature ids? (in addition to having a list of
           feature_refs) Should the Genome object contain a list of
           contig_ids too? @optional assembly_ref quality close_genomes
           analysis_events features source_id source contigs contig_ids
           publications md5 taxonomy gc_content complete dna_size num_contigs
           contig_lengths contigset_ref @metadata ws gc_content as GC content
           @metadata ws taxonomy as Taxonomy @metadata ws md5 as MD5
           @metadata ws dna_size as Size @metadata ws genetic_code as Genetic
           code @metadata ws domain as Domain @metadata ws source_id as
           Source ID @metadata ws source as Source @metadata ws
           scientific_name as Name @metadata ws length(close_genomes) as
           Close genomes @metadata ws length(features) as Number features
           @metadata ws num_contigs as Number contigs) -> structure:
           parameter "id" of type "Genome_id" (KBase genome ID @id kb),
           parameter "scientific_name" of String, parameter "domain" of
           String, parameter "genetic_code" of Long, parameter "dna_size" of
           Long, parameter "num_contigs" of Long, parameter "contigs" of list
           of type "Contig" (Type spec for a "Contig" subobject in the
           "ContigSet" object Contig_id id - ID of contig in contigset string
           md5 - unique hash of contig sequence string sequence - sequence of
           the contig string description - Description of the contig (e.g.
           everything after the ID in a FASTA file) @optional length md5
           genetic_code cell_compartment replicon_geometry replicon_type name
           description complete) -> structure: parameter "id" of type
           "Contig_id" (ContigSet contig ID @id external), parameter "length"
           of Long, parameter "md5" of String, parameter "sequence" of
           String, parameter "genetic_code" of Long, parameter
           "cell_compartment" of String, parameter "replicon_type" of String,
           parameter "replicon_geometry" of String, parameter "name" of
           String, parameter "description" of String, parameter "complete" of
           type "Bool", parameter "contig_lengths" of list of Long, parameter
           "contig_ids" of list of type "Contig_id" (ContigSet contig ID @id
           external), parameter "source" of String, parameter "source_id" of
           type "source_id" (Reference to a source_id @id external),
           parameter "md5" of String, parameter "taxonomy" of String,
           parameter "gc_content" of Double, parameter "complete" of Long,
           parameter "publications" of list of type "publication" (Structure
           for a publication (from ER API) also want to capture authors,
           journal name (not in ER)) -> tuple of size 7: parameter "id" of
           Long, parameter "source_db" of String, parameter "article_title"
           of String, parameter "link" of String, parameter "pubdate" of
           String, parameter "authors" of String, parameter "journal_name" of
           String, parameter "features" of list of type "Feature" (Structure
           for a single feature of a genome Should genome_id contain the
           genome_id in the Genome object, the workspace id of the Genome
           object, a genomeref, something else? Should sequence be in
           separate objects too? We may want to add additional fields for
           other CDM functions (e.g., atomic regulons, coexpressed fids,
           co_occurring fids,...) @optional orthologs quality
           feature_creation_event md5 location function ontology_terms
           protein_translation protein_families subsystems publications
           subsystem_data aliases annotations regulon_data atomic_regulons
           coexpressed_fids co_occurring_fids dna_sequence
           protein_translation_length dna_sequence_length) -> structure:
           parameter "id" of type "Feature_id" (KBase Feature ID @id
           external), parameter "location" of list of tuple of size 4: type
           "Contig_id" (ContigSet contig ID @id external), Long, String,
           Long, parameter "type" of String, parameter "function" of String,
           parameter "ontology_terms" of mapping from String to mapping from
           String to type "OntologyData" -> structure: parameter "id" of
           String, parameter "ontology_ref" of String, parameter
           "term_lineage" of list of String, parameter "term_name" of String,
           parameter "evidence" of list of type "OntologyEvidence" (@optional
           translation_provenance alignment_evidence) -> structure: parameter
           "method" of String, parameter "method_version" of String,
           parameter "timestamp" of String, parameter
           "translation_provenance" of tuple of size 3: parameter
           "ontologytranslation_ref" of String, parameter "namespace" of
           String, parameter "source_term" of String, parameter
           "alignment_evidence" of list of tuple of size 4: parameter "start"
           of Long, parameter "stop" of Long, parameter "align_length" of
           Long, parameter "identify" of Double, parameter "md5" of String,
           parameter "protein_translation" of String, parameter
           "dna_sequence" of String, parameter "protein_translation_length"
           of Long, parameter "dna_sequence_length" of Long, parameter
           "publications" of list of type "publication" (Structure for a
           publication (from ER API) also want to capture authors, journal
           name (not in ER)) -> tuple of size 7: parameter "id" of Long,
           parameter "source_db" of String, parameter "article_title" of
           String, parameter "link" of String, parameter "pubdate" of String,
           parameter "authors" of String, parameter "journal_name" of String,
           parameter "subsystems" of list of String, parameter
           "protein_families" of list of type "ProteinFamily" (Structure for
           a protein family @optional query_begin query_end subject_begin
           subject_end score evalue subject_description release_version) ->
           structure: parameter "id" of String, parameter "subject_db" of
           String, parameter "release_version" of String, parameter
           "subject_description" of String, parameter "query_begin" of Long,
           parameter "query_end" of Long, parameter "subject_begin" of Long,
           parameter "subject_end" of Long, parameter "score" of Double,
           parameter "evalue" of Double, parameter "aliases" of list of
           String, parameter "orthologs" of list of tuple of size 2: String,
           Double, parameter "annotations" of list of type "annotation" (a
           notation by a curator of the genome object) -> tuple of size 3:
           parameter "comment" of String, parameter "annotator" of String,
           parameter "annotation_time" of Double, parameter "subsystem_data"
           of list of type "subsystem_data" (Structure for subsystem data
           (from CDMI API)) -> tuple of size 3: parameter "subsystem" of
           String, parameter "variant" of String, parameter "role" of String,
           parameter "regulon_data" of list of type "regulon_data" (Structure
           for regulon data (from CDMI API)) -> tuple of size 3: parameter
           "regulon_id" of String, parameter "regulon_set" of list of type
           "Feature_id" (KBase Feature ID @id external), parameter "tfs" of
           list of type "Feature_id" (KBase Feature ID @id external),
           parameter "atomic_regulons" of list of type "atomic_regulon"
           (Structure for an atomic regulon (from CDMI API)) -> tuple of size
           2: parameter "atomic_regulon_id" of String, parameter
           "atomic_regulon_size" of Long, parameter "coexpressed_fids" of
           list of type "coexpressed_fid" (Structure for coexpressed fids
           (from CDMI API)) -> tuple of size 2: parameter "scored_fid" of
           type "Feature_id" (KBase Feature ID @id external), parameter
           "score" of Double, parameter "co_occurring_fids" of list of type
           "co_occurring_fid" (Structure for co-occurring fids (from CDMI
           API)) -> tuple of size 2: parameter "scored_fid" of type
           "Feature_id" (KBase Feature ID @id external), parameter "score" of
           Double, parameter "quality" of type "Feature_quality_measure"
           (@optional weighted_hit_count hit_count existence_priority
           overlap_rules pyrrolysylprotein truncated_begin truncated_end
           existence_confidence frameshifted selenoprotein) -> structure:
           parameter "truncated_begin" of type "Bool", parameter
           "truncated_end" of type "Bool", parameter "existence_confidence"
           of Double, parameter "frameshifted" of type "Bool", parameter
           "selenoprotein" of type "Bool", parameter "pyrrolysylprotein" of
           type "Bool", parameter "overlap_rules" of list of String,
           parameter "existence_priority" of Double, parameter "hit_count" of
           Double, parameter "weighted_hit_count" of Double, parameter
           "feature_creation_event" of type "Analysis_event" (@optional
           tool_name execution_time parameters hostname) -> structure:
           parameter "id" of type "Analysis_event_id", parameter "tool_name"
           of String, parameter "execution_time" of Double, parameter
           "parameters" of list of String, parameter "hostname" of String,
           parameter "contigset_ref" of type "ContigSet_ref" (Reference to a
           ContigSet object containing the contigs for this genome in the
           workspace @id ws KBaseGenomes.ContigSet), parameter "assembly_ref"
           of type "Assembly_ref" (Reference to an Assembly object in the
           workspace @id ws KBaseGenomeAnnotations.Assembly), parameter
           "quality" of type "Genome_quality_measure" (@optional
           frameshift_error_rate sequence_error_rate) -> structure: parameter
           "frameshift_error_rate" of Double, parameter "sequence_error_rate"
           of Double, parameter "close_genomes" of list of type
           "Close_genome" (@optional genome closeness_measure) -> structure:
           parameter "genome" of type "Genome_id" (KBase genome ID @id kb),
           parameter "closeness_measure" of Double, parameter
           "analysis_events" of list of type "Analysis_event" (@optional
           tool_name execution_time parameters hostname) -> structure:
           parameter "id" of type "Analysis_event_id", parameter "tool_name"
           of String, parameter "execution_time" of Double, parameter
           "parameters" of list of String, parameter "hostname" of String,
           parameter "hidden" of type "boolean" (A boolean - 0 for false, 1
           for true. @range (0, 1))
        :returns: instance of type "SaveGenomeResult" -> structure: parameter
           "info" of type "object_info" (Information about an object,
           including user provided metadata. obj_id objid - the numerical id
           of the object. obj_name name - the name of the object. type_string
           type - the type of the object. timestamp save_date - the save date
           of the object. obj_ver ver - the version of the object. username
           saved_by - the user that saved or copied the object. ws_id wsid -
           the workspace containing the object. ws_name workspace - the
           workspace containing the object. string chsum - the md5 checksum
           of the object. int size - the size of the object in bytes.
           usermeta meta - arbitrary user-supplied metadata about the
           object.) -> tuple of size 11: parameter "objid" of type "obj_id"
           (The unique, permanent numerical ID of an object.), parameter
           "name" of type "obj_name" (A string used as a name for an object.
           Any string consisting of alphanumeric characters and the
           characters |._- that is not an integer is acceptable.), parameter
           "type" of type "type_string" (A type string. Specifies the type
           and its version in a single string in the format
           [module].[typename]-[major].[minor]: module - a string. The module
           name of the typespec containing the type. typename - a string. The
           name of the type as assigned by the typedef statement. major - an
           integer. The major version of the type. A change in the major
           version implies the type has changed in a non-backwards compatible
           way. minor - an integer. The minor version of the type. A change
           in the minor version implies that the type has changed in a way
           that is backwards compatible with previous type definitions. In
           many cases, the major and minor versions are optional, and if not
           provided the most recent version will be used. Example:
           MyModule.MyType-3.1), parameter "save_date" of type "timestamp" (A
           time in the format YYYY-MM-DDThh:mm:ssZ, where Z is either the
           character Z (representing the UTC timezone) or the difference in
           time to UTC in the format +/-HHMM, eg: 2012-12-17T23:24:06-0500
           (EST time) 2013-04-03T08:56:32+0000 (UTC time)
           2013-04-03T08:56:32Z (UTC time)), parameter "version" of Long,
           parameter "saved_by" of type "username" (Login name of a KBase
           user account.), parameter "wsid" of type "ws_id" (The unique,
           permanent numerical ID of a workspace.), parameter "workspace" of
           type "ws_name" (A string used as a name for a workspace. Any
           string consisting of alphanumeric characters and "_", ".", or "-"
           that is not an integer is acceptable. The name may optionally be
           prefixed with the workspace owner's user name and a colon, e.g.
           kbasetest:my_workspace.), parameter "chsum" of String, parameter
           "size" of Long, parameter "meta" of type "usermeta" (User provided
           metadata about an object. Arbitrary key-value pairs provided by
           the user.) -> mapping from String to String
        """
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN save_one_genome

        genome_interface = GenomeInterface(self.cfg)
        returnVal = genome_interface.save_one_genome(params)
        #END save_one_genome

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method save_one_genome return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]
    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK", 'message': "", 'version': self.VERSION, 
                     'git_url': self.GIT_URL, 'git_commit_hash': self.GIT_COMMIT_HASH}
        #END_STATUS
        return [returnVal]
