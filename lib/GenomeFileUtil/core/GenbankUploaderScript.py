#!/usr/bin/env python

# standard library imports
import os
import sys
import logging
import re
import hashlib
import time 
import traceback 
import os.path 
import datetime
import shutil
#import sqlite3 
#try: 
#    import cPickle as cPickle 
#except: 
#    import pickle as cPickle 
from string import digits
from string import maketrans
from collections import OrderedDict

try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

# 3rd party imports
import simplejson
from Bio.Seq import Seq
from Bio.Alphabet import IUPAC, generic_dna

# KBase imports
import biokbase.Transform.script_utils as script_utils
import biokbase.Transform.TextFileDecoder as TextFileDecoder
import biokbase.workspace.client 
from AssemblyUtil.AssemblyUtilClient import AssemblyUtil
from KBaseReport.KBaseReportClient import KBaseReport
#from doekbase.data_api.annotation.genome_annotation.api import GenomeAnnotationAPI, GenomeAnnotationClientAPI

def insert_newlines(s, every): 
    lines = [] 
    for i in xrange(0, len(s), every): 
        lines.append(s[i:i+every]) 
    return "\n".join(lines)+"\n" 

def represents_int(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False


# transformation method that can be called if this module is imported
# Note the logger has different levels it could be run.  
# See: https://docs.python.org/2/library/logging.html#logging-levels
#
# The default level is set to INFO which includes everything except DEBUG
#@profile
def upload_genome(shock_service_url=None,
                  handle_service_url=None,
                  workspace_service_url=None,
                  callback_url=None,

                  input_directory=None, 

                  shock_id=None, handle_id=None,

                  workspace_name=None,
                  core_genome_name=None,

                  taxon_wsname=None,
                  taxon_lookup_obj_name=None,
                  taxon_reference = None,

                  exclude_ontologies=None,
                  ontology_wsname=None,
                  ontology_GO_obj_name = None,
                  ontology_PO_obj_name = None,

                  release= None,
                  source=None,
                  type=None,
                  genetic_code=None,
                  generate_ids_if_needed=None,

                  provenance=None,
                  usermeta=None,

                  level=logging.INFO, logger=None):
    """
    Uploads CondensedGenomeAssembly
    Args:
        shock_service_url: A url for the KBase SHOCK service.
        input_fasta_directory: The directory where files will be read from.
        level: Logging level, defaults to logging.INFO.
        
    Returns:
        JSON file on disk that can be saved as a KBase workspace object.
    Authors:
        Jason Baumohl, Matt Henderson
    """

    if logger is None:
        logger = script_utils.stderrlogger(__file__)
    token = os.environ.get('KB_AUTH_TOKEN') 

    logger.info("WS URL : " + str(workspace_service_url))
    logger.info("HANDLE URL : " + str(handle_service_url))
    logger.info("SHOCK URL : " + str(shock_service_url))
    logger.info("CALLBACK URL : " + str(callback_url))

    ws_client = biokbase.workspace.client.Workspace(workspace_service_url)
    workspace_object = ws_client.get_workspace_info({'workspace':workspace_name}) 
    workspace_name = workspace_object[1] 
    taxon_workspace_object = ws_client.get_workspace_info({'workspace':taxon_wsname}) 
    taxon_workspace_id = taxon_workspace_object[0] 

    report = StringIO() #variable to put warnings report into.  For UI widget reports output tab

    if exclude_ontologies is not None:
        if exclude_ontologies != 1:
            exclude_ontologies = 0
    
    [genome, taxon_id, source_name, genbank_time_string, contig_information_dict,
     source_file_name, input_file_name, locus_name_order, list_of_features,
     ontology_terms_not_found, cds_list, mrna_list, fasta_file_name] = _load_data(
                        exclude_ontologies, generate_ids_if_needed, input_directory,
                        genetic_code, core_genome_name, source, ws_client, 
                        ontology_wsname, ontology_GO_obj_name, ontology_PO_obj_name, 
                        taxon_wsname, taxon_workspace_id, taxon_lookup_obj_name, 
                        taxon_reference, report, logger)

    return _save_data(genome, core_genome_name, taxon_id, source_name, genbank_time_string, 
                      contig_information_dict, provenance, source_file_name, input_file_name, 
                      locus_name_order, list_of_features, release, ontology_terms_not_found, 
                      type, usermeta, token, ws_client, workspace_name, workspace_service_url, 
                      handle_service_url, shock_service_url, callback_url, 
                      cds_list, mrna_list, report, input_directory, fasta_file_name, logger)        



def _load_data(exclude_ontologies, generate_ids_if_needed, input_directory, genetic_code,
               core_genome_name, source,
               ws_client, ontology_wsname, ontology_GO_obj_name, ontology_PO_obj_name,
               taxon_wsname, taxon_workspace_id, taxon_lookup_obj_name, taxon_reference,
               report, logger):
    #Get GO OntologyDictionary
    ontology_sources = _load_ontology_sources(ws_client, exclude_ontologies, ontology_wsname, 
                                              ontology_GO_obj_name, ontology_PO_obj_name,
                                              logger)

    [genetic_code, genetic_code_supplied] = _validate_generic_code(genetic_code, logger)

    if generate_ids_if_needed is not None:
        if generate_ids_if_needed != 1:
            generate_ids_if_needed = 0
    else:
        generate_ids_if_needed = 0

    input_files = _find_input_files(input_directory, logger, report)

    input_file_name = _join_files_skip_empty_lines(input_files)
    source_file_name = os.path.basename(input_file_name)
    print "INPUT FILE NAME :" + input_file_name + ":"

    genbank_file_handle = TextFileDecoder.open_textdecoder(input_file_name, 'ISO-8859-1') 

    #list of tuples: (first value record start byte position, second value record stop byte position)
    genbank_file_boundaries = _load_contig_boundaries(genbank_file_handle)  
    print "Number of contigs : " + str(len(genbank_file_boundaries))
   
    [organism_dict, organism] = _load_organism_info(genbank_file_handle, genbank_file_boundaries)

    genome = {'notes': ''}
    [tax_id, tax_lineage, taxon_id] = _load_taxonomy_info(ws_client, taxon_wsname, 
                                                          taxon_lookup_obj_name, taxon_reference,
                                                          organism, genetic_code_supplied, 
                                                          genetic_code, taxon_workspace_id,
                                                          logger, report, genome)

    core_scientific_name = re.sub(r'[\W_]+', '_', genome['scientific_name'])

    #CORE OBJECT NAME WILL BE EITHER PASSED IN OR GENERATED (TaxID_Source)
    #Fasta file name format is taxID_source_timestamp
    [time_string, core_genome_name, 
     fasta_file_name, source_name] = _setup_object_names(core_genome_name, source, tax_id, 
                                                         core_scientific_name)

    print "Core Genome Name :"+ core_genome_name + ":"
    print "FASTA FILE Name :"+ fasta_file_name + ":"

    now_date = datetime.datetime.now()
        
    #Parse LOCUS line from each file and grab that meta data (also establish order of the contigs)
    locus_name_order = list() #for knowing order of the genbank files/contigs
    genbank_metadata_objects = dict() #the data structure for holding the top level metadata information of each genbank file
    contig_information_dict = dict() #the data structure for holding the top level metadata information of each genbank file for the stuff needed for making the assembly.

    #HAD TO ADD "CON" as a possible division set.  Even though that does not exist according to this documentation:
    #http://www.ncbi.nlm.nih.gov/Sitemap/samplerecord.html#GenBankDivisionB
    #Found this http://www.ncbi.nlm.nih.gov/Web/Newsltr/Fall99/contig.html , oddly suggests no sequence should be associated with this.
    genbank_division_set = {'PRI','ROD','MAM','VRT','INV','PLN','BCT','VRL','PHG','SYN','UNA','EST','PAT','STS','GSS','HTG','HTC','ENV','CON'}

    #Make the Fasta file for the sequences to be written to
    fasta_file_handle = open(os.path.join(input_directory, fasta_file_name), 'w')
    
    min_date = None
    max_date = None
    genome_publication_dict = dict()

#    #Create a SQLLite database and connection.
#    if make_sql_in_memory:
#        sql_conn = sqlite3.connect(':memory:') 
#    else:
#        db_name = "GenomeAnnotation_{}.db".format(time_string) 
#        sql_conn = sqlite3.connect(db_name) 

#    sql_cursor = sql_conn.cursor() 

    #Create a protein and feature table.
#    sql_cursor.execute('''CREATE TABLE features (feature_id text, feature_type text, sequence_length integer, feature_data blob)''')
#    sql_cursor.execute('''CREATE INDEX feature_id_idx ON features (feature_id)''')
#    sql_cursor.execute('''CREATE INDEX feature_type_idx ON features (feature_type)''')
#    sql_cursor.execute('''CREATE INDEX seq_len_idx ON features (sequence_length)''')
#    sql_cursor.execute('''PRAGMA synchronous=OFF''') 

    #Feature Data structures
    list_of_features = list()

#    #Key is the gene tag (ex: gene="NAC001"), the value is a dict with feature type as the key. The value is a list of maps (one for each feature with that gene value).  
#    #The internal map stores all the key value pairs of that feature.
#    features_grouping_dict = dict() 
    
    #Feature_type_id_counter_dict  keeps track of the count of each time a specific id needed to be generated by the uploader and not the file.
    feature_type_id_counter_dict = dict()

    #Key is feature type, value is the number of occurrences of this type. Lets me know the feature containers that will need 
    #to be made and a check to insure the counts are accurate.
    feature_type_counts = dict() 

    #key feature id to be used, value 1
    feature_ids = dict()

    #Mapping from missing ontology term to number of occurrences
    ontology_terms_not_found = dict() 

    #integers used for stripping text 
    complement_len = len("complement(")
    join_len = len("join(")
    order_len = len("order(")

    genome["num_contigs"] = len(genbank_file_boundaries)

    print "NUMBER OF GENBANK RECORDS: " + str(len(genbank_file_boundaries))
    
    try:
        [min_date, max_date] = _process_contigs(genbank_file_handle, genbank_file_boundaries, tax_lineage, 
                                                genbank_division_set, min_date, max_date, organism_dict, 
                                                now_date, complement_len, join_len, order_len, source, 
                                                exclude_ontologies, ontology_sources, time_string, 
                                                genetic_code, generate_ids_if_needed,
                                                # Output part:
                                                list_of_features, genbank_metadata_objects, 
                                                contig_information_dict, locus_name_order, 
                                                genome_publication_dict, genome, fasta_file_handle, 
                                                feature_ids, feature_type_counts, 
                                                feature_type_id_counter_dict, ontology_terms_not_found,
                                                logger, report)
    finally:
        fasta_file_handle.close()
        genbank_file_handle.close()

    _check_alternative_gene_relationship(list_of_features, feature_type_id_counter_dict)
    # cds_mrna_pairs := list<tuple<cds_feature, mrna_feature>>
    cds_mrna_pairs = _match_cds_mrna_pairs(list_of_features, logger, report)

    [cds_list, mrna_list] = _extract_cdss_mrnas(list_of_features, cds_mrna_pairs, 
                                                feature_type_id_counter_dict, logger)

    _cleanup_properties(list_of_features, ['id2'])
    _cleanup_properties(cds_list, ['parent_gene2', 'product','transcript_id'])
    _cleanup_properties(mrna_list, ['parent_gene2', 'product','transcript_id'])

    genbank_time_string = "Unknown"
    if min_date and max_date:
        if min_date == max_date:
            genbank_time_string = min_date.strftime('%d-%b-%Y').upper()
        else:
            genbank_time_string = "%s to %s" %(min_date.strftime('%d-%b-%Y').upper(), 
                                               max_date.strftime('%d-%b-%Y').upper())
    
    return [genome, taxon_id, source_name, genbank_time_string, contig_information_dict, 
            source_file_name, input_file_name, locus_name_order, list_of_features, 
            ontology_terms_not_found, cds_list, mrna_list, fasta_file_name]



def _check_alternative_gene_relationship(list_of_features, feature_type_id_counter_dict):
    gene_map = {}  # gene ID -> gene
    gene2_map = {} # gene ID2 -> gene
    for f in list_of_features:
        if f["type"] == "gene":
            gene_map[f["id"]] = f
            if "id2" in f:
                gene2_map[f["id2"]] = f
    for feature_object in list_of_features:
        gene_feature_id = feature_object.get("parent_gene")
        if (not gene_feature_id) or (gene_feature_id not in gene_map):
            gene_feature_id2 = feature_object.get("parent_gene2")
            if gene_feature_id2 and gene_feature_id2 in gene2_map:
                gene = gene2_map[gene_feature_id2]
                gene_feature_id = gene.get("id")
                if not gene_feature_id:
                    gene_feature_id = _generate_feature_id_by_type("gene", 
                                                                   feature_type_id_counter_dict)
                    gene["id"] = gene_feature_id
                feature_object["parent_gene"] = gene_feature_id



def _match_cds_mrna_pairs(list_of_features, logger, report):
    # Let's group CDSs and mRNSs by connection to the same gene:
    gene_cds_mrna_map = {}  # {<gene_id> -> {<product> -> {'cds_list': [], 'mrna_list': []}}
    for feature_object in list_of_features:
        feature_type = feature_object['type']
        if feature_type != "CDS" and feature_type != "mRNA":
            continue
        gene_feature_id = feature_object.get("parent_gene")
        if not gene_feature_id:
            continue
        gene_feature_list = None
        if gene_feature_id in gene_cds_mrna_map:
            gene_feature_list = gene_cds_mrna_map[gene_feature_id]
        else:
            gene_feature_list = []
            gene_cds_mrna_map[gene_feature_id] = gene_feature_list
        gene_feature_list.append(feature_object)

    # Let's group CDSs and mRNSs by pairs:
    cds_mrna_pairs = []  # list<tuple<cds_feature, mrna_feature>>
    for gene_id in gene_cds_mrna_map:
        feature_list = gene_cds_mrna_map[gene_id]
        [unprocessed_cds_list, 
         unprocessed_mrna_list] = _link_cds_mrna_by_property(feature_list, 
                                                             "transcript_id", cds_mrna_pairs)
        unprocessed_feature_list = [] + unprocessed_cds_list + unprocessed_mrna_list
        [unprocessed_cds_list, 
         unprocessed_mrna_list] = _link_cds_mrna_by_property(unprocessed_feature_list, 
                                                             "product", cds_mrna_pairs)
        if len(unprocessed_cds_list) > 0 and len(unprocessed_mrna_list) > 0:
            _log_report(logger, report, "Couldn't identify relationship between " + 
                        str(len(unprocessed_mrna_list)) + " mRNA(s) and " +
                        str(len(unprocessed_cds_list)) + "CDS(s) features for gene ID=" + gene_id)
    return cds_mrna_pairs



def _link_cds_mrna_by_property(feature_list, link_property, cds_mrna_pairs):
        value_cds_mrna_map = {}
        unprocessed_cds_list = []
        unprocessed_mrna_list = []
        for feature_object in feature_list:
            value = feature_object.get(link_property)
            # Let's fullfil mapping structure for value-based CDS<->mRNA connections
            if not value:
                if feature_object['type'] == "CDS":
                    unprocessed_cds_list.append(feature_object)
                else:
                    unprocessed_mrna_list.append(feature_object)
                continue
            cds_mrna_map = None
            if value in value_cds_mrna_map:
                cds_mrna_map = value_cds_mrna_map[value]
            else:
                cds_mrna_map = {'cds_list': [], 'mrna_list': []}
                value_cds_mrna_map[value] = cds_mrna_map
            if feature_object['type'] == "CDS":
                cds_mrna_map['cds_list'].append(feature_object)
            else:
                cds_mrna_map['mrna_list'].append(feature_object)
        
        unpaired_cds_list = []
        unpaired_mrna_list = []
        for value in value_cds_mrna_map:
            cds_list = value_cds_mrna_map[value]['cds_list']
            mrna_list = value_cds_mrna_map[value]['mrna_list']
            if len(cds_list) == 1 and len(mrna_list) == 1:
                cds_mrna_pairs.append([cds_list[0], mrna_list[0]])
            else:
                unpaired_cds_list.extend(cds_list)
                unpaired_mrna_list.extend(mrna_list)
        if len(unpaired_cds_list) == 1 and len(unpaired_mrna_list) == 1:
            cds_mrna_pairs.append([unpaired_cds_list[0], unpaired_mrna_list[0]])
            return [[], []]
        unprocessed_cds_list.extend(unpaired_cds_list)
        unprocessed_mrna_list.extend(unpaired_mrna_list)
        return [unprocessed_cds_list, unprocessed_mrna_list]



def _extract_cdss_mrnas(list_of_features, cds_mrna_pairs, feature_type_id_counter_dict, logger):
    _log_report(logger, None, "CDS-mRNA links: " + str(len(cds_mrna_pairs)))
    id_to_gene_map = {}  # feature_id -> gene
    cds_list = []
    mrna_list = []
    for feature in list_of_features:
        if feature["type"] == "gene":
            id_to_gene_map[feature["id"]] = feature
        elif feature["type"] == "CDS":
            cds_list.append(feature)
        elif feature["type"] == "mRNA":
            mrna_list.append(feature)
    _log_report(logger, None, "Number of CDSs: " + str(len(cds_list)))
    _log_report(logger, None, "Number of mRNAs: " + str(len(mrna_list)))
    # Filtering out all other features except CDSs
    list_of_features[:] = [feature for feature in list_of_features if (feature["type"] != "CDS" and
                                                                       feature["type"] != "mRNA")]
    _log_report(logger, None, "Number of other features: " + str(len(list_of_features)))

    for cds_mrna_pair in cds_mrna_pairs:
        cds = cds_mrna_pair[0]
        cds["parent_mrna"] = "found"
        mrna = cds_mrna_pair[1]
        keys_to_del = [key for key in mrna if key not in ["id", "location", "md5", "parent_gene"]]
        for key in keys_to_del:
            del mrna[key]
        
    # Check integrity between genes, CDSs and mRNAs
    for cds in cds_list:
        gene = None
        gene_id = None
        if "parent_gene" in cds:
            gene_id = cds["parent_gene"]
            gene = id_to_gene_map.get(gene_id)
        if gene:
            _propagate_cds_props_to_gene(cds, gene)
        else:  # We generate new Gene base on CDS
            if not gene_id:
                gene_id = _generate_feature_id_by_type("gene", feature_type_id_counter_dict)
            
            gene = cds.copy()  # I don't think we need deepcopy here (but we should be careful)
            gene["id"] = gene_id
            list_of_features.append(gene)
            id_to_gene_map[gene_id] = gene
            
        cds["parent_gene"] = gene_id
        
        if "parent_mrna" not in cds:  # mRNA was not found for CDS
            mrna = {"id": _generate_feature_id_by_type("mRNA", feature_type_id_counter_dict),
                    "location": cds["location"], "md5": "", "parent_gene": gene_id}
            mrna_list.append(mrna)
            cds_mrna_pairs.append([cds, mrna])

        if "ontology_terms" not in cds:
            cds["ontology_terms"] = {}
        if "function" not in cds:
            cds["function"] = ""
        if "aliases" not in cds:
            cds["aliases"] = []

    _rename_duplicated_ids(cds_list, "id")
    _rename_duplicated_ids(mrna_list, "id")
    
    # Now we can add cross-refs between genes, CDSs and mRNAs
    for cds_mrna_pair in cds_mrna_pairs:
        cds = cds_mrna_pair[0]
        mrna = cds_mrna_pair[1]
        cds["parent_mrna"] = mrna["id"]
        mrna["cds"] = cds["id"]
        mrna["parent_gene"] = cds["parent_gene"]
        gene = id_to_gene_map[cds["parent_gene"]]
        if "cdss" in gene:
            gene["cdss"].append(cds["id"])
        else:
            gene["cdss"] = [cds["id"]]
        if "mrnas" in gene:
            gene["mrnas"].append(mrna["id"])
        else:
            gene["mrnas"] = [mrna["id"]]

    # Let's delete orphan mRNAs
    mrna_list[:] = [mrna for mrna in mrna_list if 'cds' in mrna]

    return [cds_list, mrna_list]



def _cleanup_properties(obj_list, props_to_delete):
    for obj in obj_list:
        for prop in props_to_delete:
            if prop in obj:
                del obj[prop]



def _propagate_cds_props_to_gene(cds, gene):
    # Check gene function
    if "function" not in gene or gene["function"] is None or len(gene["function"]) == 0:
        gene["function"] = cds.get("function", "")
    # Put longest protein_translation to gene
    if "protein_translation" not in gene or (len(gene["protein_translation"]) <
                                             len(cds["protein_translation"])):
        gene["protein_translation"] = cds["protein_translation"]
        gene["protein_translation_length"] = len(cds["protein_translation"])
    # Merge cds["aliases"] -> gene["aliases"]
    alias_dict = {alias: True for alias in cds["aliases"] if len(alias) > 0}
    alias_dict.update({alias: True for alias in gene["aliases"] if len(alias) > 0})
    gene["aliases"] = alias_dict.keys()
    # Merge cds["ontology_terms"] -> gene["ontology_terms"]
    terms2 = cds.get("ontology_terms")
    if terms2 is not None:
        terms = gene.get("ontology_terms")
        if terms is None:
            gene["ontology_terms"] = terms2
        else:
            for source in terms2:
                if source in terms:
                    terms[source].update(terms2[source])
                else:
                    terms[source] = terms2[source]



def _generate_feature_id_by_type(feature_type, feature_type_id_counter_dict):
    if feature_type not in feature_type_id_counter_dict:
        feature_type_id_counter_dict[feature_type] = 1;
        feature_id = "%s_%s" % (feature_type, str(1)) 
    else: 
        feature_type_id_counter_dict[feature_type] += 1; 
        feature_id = "%s_%s" % (feature_type, str(feature_type_id_counter_dict[feature_type]))
    return feature_id



def _rename_duplicated_ids(list_of_features, id_field):
    id_to_cdss_map = {}  # feature_id -> list<CDS>
    for cds in list_of_features:
        if id_field not in cds or not(cds[id_field]):
            continue
        id_value = cds[id_field]
        if id_value in id_to_cdss_map:
            id_to_cdss_map[id_value].append(cds)
        else:
            id_to_cdss_map[id_value] = [cds]
    used_cds_ids = {key: True for key in id_to_cdss_map}
    # Make IDs of CDSs unique:
    for cds_id in id_to_cdss_map:
        cds_list = id_to_cdss_map[cds_id]
        if len(cds_list) > 1:
            pos = 0
            for cds in cds_list:
                new_id = None
                while True:
                    new_id = cds_id + '_' + _generate_alphabetic_suffix(pos)
                    if new_id not in used_cds_ids:
                        break
                    pos += 1
                cds[id_field] = new_id
                used_cds_ids[new_id] = True     # Not necessary but it's cleaner
                pos += 1



def _generate_alphabetic_suffix(pos):
    alphabet_size = 26
    ret = ""
    while True:
        ret = chr(ord('A') + (pos % alphabet_size)) + ret
        pos = int(pos / alphabet_size)
        if pos == 0:
            break
    return ret



def _save_data(genome, core_genome_name, taxon_id, source_name, genbank_time_string, 
               contig_information_dict, provenance, source_file_name, input_file_name,
               locus_name_order, list_of_features, release, ontology_terms_not_found,
               genome_type, usermeta, token, ws_client, workspace_name, workspace_service_url,
               handle_service_url, shock_service_url, callback_url, 
               cds_list, mrna_list, report, input_directory, fasta_file_name, logger):
    ##########################################
    #ASSEMBLY CREATION PORTION  - consume Fasta File
    ##########################################

    logger.info("Calling FASTA to Assembly Uploader")
    assembly_reference = "%s/%s_assembly" % (workspace_name,core_genome_name)
    try:
        fasta_file_path = os.path.join(input_directory, fasta_file_name)

        print "HANDLE SERVICE URL " + handle_service_url

        aUtil = AssemblyUtil(callback_url)
        assembly_ref = aUtil.save_assembly_from_fasta(
                                                {'file':
                                                    {'path': fasta_file_path},
                                                 'workspace_name': workspace_name,
                                                 'assembly_name': "%s_assembly" % (core_genome_name),
                                                 'taxon_ref': taxon_id,
                                                 'contig_info': contig_information_dict})
        # Note: still missing source and date_string fields

    except Exception, e: 
        logger.exception(e) 
        raise

    logger.info("Assembly Uploaded")
    
    assembly_info = ws_client.get_object_info_new({'objects': [{'ref': assembly_reference}],
                                                   'includeMetadata': 1})[0]
    assembly_meta = assembly_info[10]
    gc_content = float(assembly_meta.get("GC content"))
    dna_size = int(assembly_meta.get("Size"))

#    sys.exit(1)

    #Do size check of the features
#    sql_cursor.execute("select sum(length(feature_data)) from features where feature_type = ?", (feature_type,))
#    sql_cursor.execute("select sum(length(feature_data)) from features")
#    for row in sql_cursor:
#        data_length = row[0]

#    if data_length < 900000000:
        #Size is probably ok Try the save
        #Retrieve the features from the sqllite DB
#        sql_cursor.execute("select feature_id, feature_data from features")

#        for row in sql_cursor: 
#            feature_id = row[0]
#            feature_data = cPickle.loads(str(row[1])) 
#            list_of_features.append(feature_data)

#    else:
        #Features too large
        #raising an error for now.
#        raise Exception("This genome can not be saved due to the resulting object being too large for the workspace")

    #Save genome
    #Then Finally store the GenomeAnnotation.                                                                            

    shock_id = None
    handle_id = None
    if shock_id is None:
        shock_info = script_utils.upload_file_to_shock(logger, shock_service_url, input_file_name, token=token)
        shock_id = shock_info["id"]
        handles = script_utils.getHandles(logger, shock_service_url, handle_service_url, [shock_id], [handle_id], token)   
        handle_id = handles[0]

    genome['genbank_handle_ref'] = handle_id
    # setup provenance
    provenance_action = {"script": __file__, "script_ver": "0.1", "description": "features from upload from %s" % (source_name)}
    genome_annotation_provenance = []
    if provenance is not None:
        genome_annotation_provenance = provenance
    genome_annotation_provenance.append(provenance_action)
    genome_object_name = core_genome_name 
    genome['type'] = genome_type 
    if genome_type == "Reference":
        genome['reference_annotation'] = 1
    else:
        genome['reference_annotation'] = 0
    genome['taxon_ref'] = taxon_id
    genome['original_source_file_name'] = source_file_name
    genome['assembly_ref'] =  assembly_reference 
    genome['id'] = genome_object_name
    genome['source'] = source_name
    temp_source_id = locus_name_order[0]
    if len(locus_name_order) > 1:
        temp_source_id += ' (' + str(len(locus_name_order) - 1) + ' more accessions)'
    genome['source_id'] = temp_source_id
    genome['external_source_origination_date'] = genbank_time_string
    genome['features'] = list_of_features
    genome['cdss'] = cds_list
    genome['mrnas'] = mrna_list
    genome['gc_content'] = gc_content
    genome['dna_size'] = dna_size
    if release is not None:
        genome['release'] = release
    if len(ontology_terms_not_found) > 0:
        report.write("\nThere were ontologies in the source file that were not found in the onology database.\n\
These are like to be deprecated terms.\n\
Below is a list of the term and the countof the number of features that contained that term:\n")

        for term in ontology_terms_not_found:
            report.write("{} --- {}\n".format(term,str(ontology_terms_not_found[term])))
        report.write("\n")

#    print "Genome id %s" % (genome['id'])
 
    logger.info("Attempting Genome save for %s" % (genome_object_name))
#    while genome_annotation_not_saved:
#        try:
    genome_annotation_info =  ws_client.save_objects({"workspace":workspace_name,
                                                      "objects":[ { "type":"KBaseGenomes.Genome",
                                                                    "data":genome,
                                                                    "name": genome_object_name,
                                                                    "provenance":genome_annotation_provenance,
                                                                    "meta":usermeta
                                                                }]}) 
#            genome_annotation_not_saved = False 
    logger.info("Genome saved for %s" % (genome_object_name))
#        except biokbase.workspace.client.ServerError as err: 
#            raise 

#    if not make_sql_in_memory:
#        os.remove(db_name) 

    logger.info("Conversions completed.")
    report.write("\n\nGENOME AND ASSEMBLY OBJECTS HAVE BEEN SUCESSFULLY SAVED.")


    output_data_ref = "{}/{}".format(workspace_name,genome_object_name)
    reportValue = report.getvalue()
    if len(reportValue) > 900000:
        reportValue = reportValue[:900000] + "\n...Report was truncated because it's too long."
    reportObj = {
        'objects_created':[{'ref':output_data_ref, 'description':'Assembled contigs'}],
        'text_message':reportValue
    }
    report_kb = KBaseReport(callback_url)
    report_info = report_kb.create({'report':reportObj, 'workspace_name':workspace_name})
    report.close

    return {
        'genome_info': genome_annotation_info[0],
        'report_name': report_info['name'],
        'report_ref': report_info['ref']
    }



def _find_input_files(input_directory, logger, report):
    logger.info("Scanning for Genbank Format files.") 
    valid_extensions = [".gbff",".gbk",".gb",".genbank",".dat", ".gbf"] 
 
    files = os.listdir(os.path.abspath(input_directory)) 
    print "FILES : " + str(files)
    genbank_files = [x for x in files if os.path.splitext(x)[-1] in valid_extensions] 

    if (len(genbank_files) == 0): 
        raise Exception("The input directory does not have one of the following extensions %s." % (",".join(valid_extensions))) 
  
    logger.info("Found {0}".format(str(genbank_files))) 
 
    input_files = []
    for genbank_file in genbank_files:
        input_files.append(os.path.join(input_directory,genbank_file)) 
 
    return input_files



def _load_ontology_sources(ws_client, exclude_ontologies, ontology_wsname,
                           ontology_GO_obj_name, ontology_PO_obj_name, logger):
    ontology_sources = dict()

    if exclude_ontologies == 0:
        #    ontologies = ws_client.get_objects2({'objects': [{'workspace': 'KBaseOntology', 'name':'gene_ontology'}]}) 
        #    go_ontology = ontologies['data'][0]['data'] 
        logger.info("Retrieving Ontology databases.") 
        ontologies = ws_client.get_objects( [{'workspace':ontology_wsname,
                                              'name':ontology_GO_obj_name},
                                             {'workspace':ontology_wsname,
                                              'name':ontology_PO_obj_name}])
        logger.info("Ontology databases retrieved.") 
        
        ontology_sources["GO"] = ontologies[0]['data']['term_hash']
        ontology_sources["PO"] = ontologies[1]['data']['term_hash']
        del ontologies
#    go_ontologies = ws_client.get_objects( [{'workspace':'KBaseOntology',
#                                             'name':'gene_ontology'}])
#    logger.info("Retrieved GO Ontology database, starting PO") 
#    po_ontologies = ws_client.get_objects( [{'workspace':'KBaseOntology',
#                                          'name':'plant_ontology'}])
#    logger.info("Retrieved PO Ontology database") 
#    ontology_sources["GO"] = go_ontologies[0]['data']['term_hash']
#    ontology_sources["PO"] = po_ontologies[0]['data']['term_hash']
#    del go_ontologies
#    del po_ontologies
    return ontology_sources



def _validate_generic_code(genetic_code, logger):
    logger.info("GENETIC_CODE ENTERED : {}".format(str(genetic_code)))
    genetic_code_supplied = False
    if genetic_code is not None:
        genetic_code_supplied = True
        valid_genetic_codes = [1,2,3,4,5,6,9,10,11,12,13,14,16,21,22,23,24,25,26]
        if genetic_code not in valid_genetic_codes:
            raise Exception("The entered genetic code of {} is not a valid genetic code, please see http://www.ncbi.nlm.nih.gov/Taxonomy/Utils/wprintgc.cgi".format(str(genetic_code)))
    else:
        genetic_code = 1
    return [genetic_code, genetic_code_supplied]



def _join_files_skip_empty_lines(input_files):
    """ Applies strip to each line of each input file.
    Args:
        input_files: Paths to input files in Genbank format.
    Returns:
        Path to resulting file (currenly it's the same file as input).
    """
    if len(input_files) == 0:
        raise ValueError("NO GENBANK FILE")
    temp_dir = os.path.join(os.path.dirname(input_files[0]), "combined")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    ret_file = os.path.join(temp_dir, os.path.basename(input_files[0]))

    #take in Genbank file and remove all empty lines from it.
    with open(ret_file,'w', buffering=2**20 ) as f_out:
        for input_file in input_files:
            with open(input_file,'r') as f_in:
                for line in f_in:
                    line = line.rstrip('\r\n')
                    if line.strip():
                        f_out.write(line + '\n')
    return ret_file



def _load_contig_boundaries(genbank_file_handle):
    """ Loads boundaries of contigs (text blocks separated by '//' line)
    Args:
        genbank_file_handle: File handle of input file in Genbank format.
    Returns:
        List of tuples (where each tuple is [start,end] pair of to 
        pointers to file position).
    """
    genbank_file_boundaries = list()  
    #list of tuples: (first value record start byte position, second value record stop byte position)

    #If file is over a 1GB need to do SQLLite on disc
    #if os.stat(input_file_name) > 1073741824 :
    #    make_sql_in_memory = True
        
    start_position = 0
    current_line = genbank_file_handle.readline()
    last_line = None
    while (current_line != ''):
        last_line = current_line 
        if current_line.startswith("//"):
            end_position =  genbank_file_handle.tell() - len(current_line)
            genbank_file_boundaries.append([start_position,end_position])
#                last_start_position = start_position
            start_position = genbank_file_handle.tell()
        current_line = genbank_file_handle.readline()

    if not last_line.startswith("//"):
        end_position = genbank_file_handle.tell()
        genbank_file_boundaries.append([start_position,end_position])

    return genbank_file_boundaries



def _load_organism_info(genbank_file_handle, genbank_file_boundaries):
    organism_dict = dict() 
    organism = None
    if len(genbank_file_boundaries) < 1 :
        raise ValueError("Error no genbank record found in the input file")
    else:
        byte_coordinates = genbank_file_boundaries[0]
        genbank_file_handle.seek(byte_coordinates[0]) 
        temp_record = genbank_file_handle.read(byte_coordinates[1] - byte_coordinates[0]) 

        record_lines = temp_record.split("\n")
        for record_line in record_lines:
            if record_line.startswith("  ORGANISM  "):
                organism = record_line[12:]
                print "Organism Line :" + record_line + ":"
                print "Organism :" + organism + ":"
                organism_dict[organism] = 1
                break
        return [organism_dict, organism]



def _load_taxonomy_info(ws_client, taxon_wsname, taxon_lookup_obj_name, taxon_reference,
                        organism, genetic_code_supplied, genetic_code, taxon_workspace_id, 
                        logger, report, genome):
    tax_id = 0;
    tax_lineage = None;

    genomes_without_taxon_refs = list()

    logger.info("Looking up taxonomy")
    if taxon_reference is None:
        #Get the taxon_lookup_object
        taxon_lookup = ws_client.get_objects( [{'workspace':taxon_wsname,
                                                'name':taxon_lookup_obj_name}])
        if ((organism is not None) and (organism[0:3] in taxon_lookup[0]['data']['taxon_lookup'])):
            if organism in taxon_lookup[0]['data']['taxon_lookup'][organism[0:3]]:
                tax_id = taxon_lookup[0]['data']['taxon_lookup'][organism[0:3]][organism] 
                taxon_object_name = "%s_taxon" % (str(tax_id))
            else:
                genomes_without_taxon_refs.append(organism)
                taxon_object_name = "unknown_taxon"
                genome['notes'] = "Unable to find taxon for this organism : {}.".format(organism )
                genome['scientific_name'] = "Unconfirmed Organism: {}".format(organism )
                report.write("Unable to find taxon for this organism : {}.\n\n".format(organism ))
        else: 
            genomes_without_taxon_refs.append(organism)
            taxon_object_name = "unknown_taxon"
            genome['notes'] = "Unable to find taxon for this organism : {}.".format(organism )
            genome['scientific_name'] = "Unconfirmed Organism: {}".format(organism )
            report.write("Unable to find taxon for this organism : {}.\n\n".format(organism ))
        del taxon_lookup

        try: 
            logger.info("attempting to link to " + taxon_wsname + '/' + taxon_object_name)
            taxon_info = ws_client.get_objects([{"workspace": taxon_wsname, 
                                                 "name": taxon_object_name}])
        except Exception, e: 
            raise Exception("The taxon " + taxon_object_name + " from workspace " + str(taxon_workspace_id) + " does not exist. Error was:" + str(e))
    
        taxon_id = "%s/%s/%s" % (taxon_info[0]["info"][6], taxon_info[0]["info"][0], taxon_info[0]["info"][4]) 
        if not genetic_code_supplied:
            genetic_code = taxon_info[0]["data"]["genetic_code"]
        elif genetic_code != taxon_info[0]["data"]["genetic_code"]:
            #Supplied genetic code differs from taxon genetic code.  Add warning to genome notes
            temp_notes = ""
            if "notes" in genome:
                temp_notes = "{} ".format(genome["notes"])
            genome["notes"] = "{}The supplied genetic code of {} differs from the taxon genetic code of {}. The supplied genetic code is being used.".format(temp_notes,genetic_code, taxon_info[0]["data"]["genetic_code"])
            report.write("The supplied genetic code of {} differs from the taxon genetic code of {}. The supplied genetic code is being used.\n\n".format(genetic_code, taxon_info[0]["data"]["genetic_code"]))
        else:
            temp_notes = ""
            if "notes" in genome:
                temp_notes = "{} ".format(genome["notes"])
            genome["notes"] = "{}The genetic code of {} was supplied by the user.".format(temp_notes,genetic_code, taxon_info[0]["data"]["genetic_code"])
            report.write("The genetic code of {} was supplied by the user.\n\n".format(genetic_code, taxon_info[0]["data"]["genetic_code"]))

        genome['genetic_code'] = genetic_code
#            print "Found name : " + taxon_object_name + " id: " + taxon_id
#            print "TAXON OBJECT TYPE : " + taxon_info[0]["info"][2]
        if not taxon_info[0]["info"][2].startswith("KBaseGenomeAnnotations.Taxon"):
            raise Exception("The object retrieved for the taxon object is not actually a taxon object.  It is {}".format(taxon_info[0]["info"][2]))
        if 'scientific_name' not in genome:
            genome['scientific_name'] = taxon_info[0]['data']['scientific_name']
        genome['domain'] = taxon_info[0]['data']['domain']

    else:

        logger.info("Exact reference provided, using:" + str(taxon_reference))
        try: 
            taxon_info = ws_client.get_objects([{"ref": taxon_reference}])
            taxon_id = "%s/%s/%s" % (taxon_info[0]["info"][6], taxon_info[0]["info"][0], taxon_info[0]["info"][4]) 
        except Exception, e:
            raise Exception("The taxon reference " + str(taxon_reference) + " does not correspond to a workspace object. Error was:" + str(e))
    
        print "TAXON OBJECT TYPE : " + taxon_info[0]["info"][2] 
        if not taxon_info[0]["info"][2].startswith("KBaseGenomeAnnotations.Taxon"):
            raise Exception("The object retrieved for the taxon object is not actually a taxon object.  It is " + taxon_info[0]["info"][2])
        if not genetic_code_supplied:
            genetic_code = taxon_info[0]["data"]["genetic_code"]
        elif genetic_code != taxon_info[0]["data"]["genetic_code"]:
            #Supplied genetic code differs from taxon genetic code.  Add warning to genome notes
            temp_notes = ""
            if "notes" in genome:
                temp_notes = "{} ".format(genome["notes"])
            genome['notes'] ="{}  The supplied genetic code of {} differs from the taxon genetic code of {}. The supplied genetic code is being used.".format(temp_notes,genetic_code, 
                                                                                                                                                           taxon_info[0]["data"]["genetic_code"])
        report.write("The supplied genetic code of {} differs from the taxon genetic code of {}. The supplied genetic code is being used.\n\n".format(genetic_code, 
                                                                                                                                                              taxon_info[0]["data"]["genetic_code"]))
        genome['genetic_code'] = genetic_code
        genome['scientific_name'] = taxon_info[0]['data']['scientific_name']
        genome['domain'] = taxon_info[0]['data']['domain']

    genome['taxonomy'] = taxon_info[0]["data"]["scientific_lineage"]
    tax_lineage = genome['taxonomy']
    return [tax_id, tax_lineage, taxon_id]

def _setup_object_names(core_genome_name, source, tax_id, core_scientific_name):
    time_string = str(datetime.datetime.fromtimestamp(time.time()).strftime('%Y_%m_%d_%H_%M_%S'))
    if core_genome_name is None:
        if source is None:
            source_name = "unknown_source"
        else:
            source_name = source
        if tax_id == 0:
            core_genome_name = "%s_%s" % (source_name,time_string) 
            fasta_file_name = "unknown_%s_%s.fa" % (source_name,time_string) 
        else:
            core_genome_name = "%s_%s" % (core_scientific_name,source_name) 
            fasta_file_name = "%s_%s.fa" % (core_scientific_name,time_string) 
    else:
        fasta_file_name = "%s_%s.fa" % (core_genome_name,time_string) 
        if source is None:
            source_name = "unknown_source"
        else:
            source_name = source
    return [time_string, core_genome_name, fasta_file_name, source_name]



def _load_blocks_for_contig(genbank_file_handle, byte_coordinates):
    genbank_file_handle.seek(byte_coordinates[0]) 
    genbank_record = genbank_file_handle.read(byte_coordinates[1] - byte_coordinates[0]) 
    try:
        annotation_part, sequence_part = genbank_record.rsplit("ORIGIN",1)
    except Exception, e:
        #sequence does not exist.
        raise Exception("This Genbank file has at least one record without a sequence.")

    #done with need for variable genbank_record. Freeing up memory
    genbank_record = None
    metadata_part, features_part = annotation_part.rsplit("FEATURES             Location/Qualifiers",1)
    return [metadata_part, features_part, sequence_part]



def _log_report(logger, report, line):
    if logger:
        logger.info(line)
    if report:
        report.write(line + "\n")


def _process_contigs(genbank_file_handle, genbank_file_boundaries, tax_lineage, genbank_division_set, min_date,
                     max_date, organism_dict, now_date, complement_len, join_len, order_len, source, 
                     exclude_ontologies, ontology_sources, time_string, genetic_code, generate_ids_if_needed,
                     # Output part:
                     list_of_features, genbank_metadata_objects, contig_information_dict, locus_name_order, 
                     genome_publication_dict, genome, fasta_file_handle, feature_ids, 
                     feature_type_counts, feature_type_id_counter_dict, ontology_terms_not_found,
                     logger, report):
    good_contig_count = 0;
    for contig_pos, byte_coordinates in enumerate(genbank_file_boundaries): 
        [metadata_part, features_part, sequence_part] = _load_blocks_for_contig(genbank_file_handle, byte_coordinates)

        [min_date, max_date, accession] = _process_metadata(contig_pos,
                                                            metadata_part, tax_lineage, genbank_division_set, 
                                                            min_date, max_date, organism_dict, now_date, 
                                                            genbank_metadata_objects, contig_information_dict, 
                                                            locus_name_order, genome_publication_dict, genome,
                                                            logger, report)
        if not accession:
            # Contig is skipped
            continue
        good_contig_count += 1

        ##################################################################################################
        #MAKE SEQUENCE PART INTO CONTIG WITH NO INTERVENING SPACES OR NUMBERS
        ##################################################################################################
        sequence_part = re.sub('[0-9]+', '', sequence_part)
        sequence_part = re.sub('\s+','',sequence_part)
        sequence_part = sequence_part.replace("?","")

        contig_length = len(sequence_part)
        if contig_length == 0:
            fasta_file_handle.close() 
            raise Exception("The genbank record %s does not have any sequence associated with it." % (accession))
            

        ##################################################################################################
        #FEATURE ANNOTATION PORTION - Build up datastructures to be able to build feature containers.
        ##################################################################################################
        #print "GOT TO FEATURE PORTION"
        features_lines = features_part.split("\n") 

        num_feature_lines = len(features_lines)
        features_list = list()

        #break up the features section into individual features.
        for feature_line_counter in range(0,(num_feature_lines)):
            feature_line = features_lines[feature_line_counter]
            if ((not feature_line.startswith("                     ")) and (feature_line.startswith("     ")) and (feature_line[5:7].strip() != "")):
                #Means a new feature:
                #
                current_feature_string = feature_line
                while ((feature_line_counter + 1) < num_feature_lines) and (features_lines[(feature_line_counter + 1)].startswith("                     ")): 
                    feature_line_counter += 1 
                    feature_line = features_lines[feature_line_counter]
                    current_feature_string += " %s" % (feature_line)

                features_list.append(current_feature_string)

            elif ((feature_line_counter + 1) < num_feature_lines): 
                feature_line_counter += 1 
                feature_line = features_lines[feature_line_counter]
        
        #Go through each feature and determine key value pairs, properties and importantly the id to use to group for interfeature_relationships.
        for feature_text in features_list:
            feature_object = _create_feature_object(feature_text, complement_len, join_len, order_len, 
                                                    contig_length, accession, sequence_part, source, 
                                                    exclude_ontologies, ontology_sources, time_string, 
                                                    genetic_code, generate_ids_if_needed, report, 
                                                    feature_ids, feature_type_counts, 
                                                    feature_type_id_counter_dict, 
                                                    ontology_terms_not_found)
            if feature_object is not None:
                list_of_features.append(feature_object)
            
#        for feature_type in feature_type_counts:
#            print "Feature " + feature_type + "  count: " + str(feature_type_counts[feature_type])

        ##################################################################################################
        #SEQUENCE PARSING PORTION  - Write out to Fasta File
        ##################################################################################################

#        print "The len of sequence part is: " + str(len(sequence_part))
#        print "The number from the record: " + genbank_metadata_objects[accession]["number_of_basepairs"]        
#        print "First 100 of sequence part : " + sequence_part[0:100] 
        fasta_file_handle.write(">{}\n".format(accession))
        #write 80 nucleotides per line
        fasta_file_handle.write(insert_newlines(sequence_part,80))
    
    if good_contig_count == 0:
        raise ValueError("No DNA/virus-RNA contigs in proper format were found")
        
    return [min_date, max_date]



def _process_metadata(contig_pos,
                      metadata_part, tax_lineage, genbank_division_set, 
                      min_date, max_date, organism_dict, now_date,
                      genbank_metadata_objects, contig_information_dict, 
                      locus_name_order, genome_publication_dict, genome,
                      logger, report):
    metadata_lines = metadata_part.split("\n")

    ##########################################
    #METADATA PARSING PORTION
    ##########################################
    accession = None
    for metadata_line in metadata_lines: 
        if metadata_line.startswith("ACCESSION   "): 
            accession = metadata_line[12:].split(' ', 1)[0]
            break
    # TODO: raise an error if accession is not set
    if accession == "unknown":
        accession = None

    #LOCUS line parsing
    locus_line_info = metadata_lines[0].split()
    if (not accession) and len(locus_line_info) >= 2 and locus_line_info[0] == 'LOCUS':
        accession = locus_line_info[1]
    
    if not accession:
        accession = "Unknown_" + str(contig_pos + 1)
    
    genbank_metadata_objects[accession] = dict()
    contig_information_dict[accession] = dict()
    locus_name_order.append(accession)
    if (len(locus_line_info) < 5):
        _log_report(logger, report, 
                    "Warning: the record with the Locus Name of %s does not have a valid Locus" +
                    "line.  It has %s space separated elements when 6 to 8 are expected " +
                    "(typically 8)." % (locus_line_info[1],str(len(locus_line_info))))
    else:
        genbank_metadata_objects[accession]["number_of_basepairs"] = locus_line_info[2]
        if locus_line_info[4].upper() != 'DNA':
            if tax_lineage is None:
                _log_report(logger, report, 
                                "Warning: the record molecule type of %s " +
                                "is not DNA and there is no tax_lineage found " +
                                "check if it is a virus" % 
                                (locus_line_info[4]))
            elif (locus_line_info[4].upper() == 'RNA' or 
                locus_line_info[4].upper() == 'SS-RNA' or 
                locus_line_info[4].upper() == 'SS-DNA'):
                if ((not tax_lineage.lower().startswith("viruses")) and 
                    (not tax_lineage.lower().startswith("viroids"))):
                    _log_report(logger, report, 
                                "Warning: the record with the Locus Name of %s is RNA, but the " +
                                "organism does not belong to Viruses or Viroids." % 
                                (locus_line_info[1]))
            else:
                _log_report(logger, report, 
                            "Warning: the record with the Locus Name of %s is not valid as the " +
                            "molecule type of '%s' , is not 'DNA' or 'RNA'. If it is RNA it must" +
                            " be a virus or a viroid." % (locus_line_info[1],locus_line_info[4]))
        genbank_metadata_objects[accession]["is_circular"] = "Unknown"
        date_text = ''
        if ((len(locus_line_info) == 7) and (locus_line_info[5] in genbank_division_set)) :
            date_text = locus_line_info[6]
        elif ((len(locus_line_info) == 8) and (locus_line_info[6] in genbank_division_set)) :
            date_text = locus_line_info[7]
            if locus_line_info[5] == "circular":
                genbank_metadata_objects[accession]["is_circular"] = "True"
                contig_information_dict[accession]["is_circ"] = 1
            elif locus_line_info[5] == "linear":
                genbank_metadata_objects[accession]["is_circular"] = "False"
                contig_information_dict[accession]["is_circ"] = 0
        elif len(locus_line_info) >= 6:
            date_text = locus_line_info[5]

    try:
        record_time = datetime.datetime.strptime(date_text, '%d-%b-%Y')
        if min_date == None:
            min_date = record_time
        elif record_time < min_date:
            min_date = record_time
        if max_date == None:
            max_date = record_time
        elif record_time > max_date:
            max_date = record_time
    except ValueError:
        exception_string = ("Warning: incorrect date format, should be 'DD-MON-YYYY', attempting" +
                            " to parse the following as a date: %s, the locus line elements: %s " %
                            (date_text, ":".join(locus_line_info)))
#            raise ValueError("Incorrect date format, should be 'DD-MON-YYYY' , attempting to parse the following as a date:" + date_text)
        _log_report(logger, report, exception_string)

    genbank_metadata_objects[accession]["external_source_origination_date"] = date_text

    num_metadata_lines = len(metadata_lines)
    metadata_line_counter = 0

    for metadata_line in metadata_lines:
        if metadata_line.startswith("DEFINITION  "):
            definition = metadata_line[12:]
            definition_loop_counter = 1
            if ((metadata_line_counter + definition_loop_counter)<= num_metadata_lines):
                next_line = metadata_lines[metadata_line_counter + definition_loop_counter]
                while (next_line.startswith("            ")) and ((metadata_line_counter + definition_loop_counter)<= num_metadata_lines) :
                    definition = "%s %s" % (definition,next_line[12:])
                    definition_loop_counter += 1
                    if ((metadata_line_counter + definition_loop_counter)<= num_metadata_lines):
                        next_line = metadata_lines[metadata_line_counter + definition_loop_counter]
                    else:
                        break
            genbank_metadata_objects[accession]["definition"] = definition 
            contig_information_dict[accession]["description"] = definition
        elif metadata_line.startswith("  ORGANISM  "): 
            organism = metadata_line[12:] 
            if organism not in organism_dict:
                _log_report(logger, report, ("There is more than one organism represented in " +
                            "these Genbank files, they do not represent single genome. First " +
                            "record's organism is %s , but %s was also found")
                            % (str(organism_dict.keys()),organism))
        elif metadata_line.startswith("COMMENT     "):
            comment = metadata_line[12:] 
            comment_loop_counter = 1 
            if ((metadata_line_counter + comment_loop_counter)<= num_metadata_lines):
                next_line = metadata_lines[metadata_line_counter + comment_loop_counter] 
                while (next_line.startswith("            ")) : 
                    comment = "%s %s" % (comment,next_line[12:]) 
                    comment_loop_counter += 1 
                    if ((metadata_line_counter + comment_loop_counter)<= num_metadata_lines):
                        next_line = metadata_lines[metadata_line_counter + comment_loop_counter]
                    else:
                        break
#                genome_comment = "%s<%s :: %s> " % (genome_comment,accession,comment)
#                genome_comment_io.write("<%s :: %s> " % (accession,comment))
        elif metadata_line.startswith("REFERENCE   "):
            _load_publication_info(metadata_lines, metadata_line_counter, now_date, 
                                   genome_publication_dict)

        metadata_line_counter += 1

    if len(genome_publication_dict) > 0 :
        genome["publications"] = genome_publication_dict.values() 

    return [min_date, max_date, accession]



def _load_publication_info(metadata_lines, metadata_line_counter, now_date,
                           genome_publication_dict):
    num_metadata_lines = len(metadata_lines)
    metadata_line = metadata_lines[metadata_line_counter]
    #PUBLICATION SECTION (long)
    authors = ''
    title = ''
    journal = ''
    pubmed = ''
    consortium = ''
    publication_key = metadata_line

    reference_loop_counter = 1
    if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines): 
        next_line = metadata_lines[metadata_line_counter + reference_loop_counter] 
    # while (next_line and re.match(r'\s', next_line) and not nextline[0].isalpha()):
    while (next_line and re.match(r'\s', next_line)):
        publication_key += next_line
        if next_line.startswith("  AUTHORS   "):
            authors = next_line[12:] 
            reference_loop_counter += 1
            if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                next_line = metadata_lines[metadata_line_counter + reference_loop_counter] 
            else:
                break
            while (next_line.startswith("            ")) :     
                authors = "%s %s" % (authors,next_line[12:]) 
                reference_loop_counter += 1
                if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines): 
                    next_line = metadata_lines[metadata_line_counter + reference_loop_counter] 
                else: 
                    break 
        elif next_line.startswith("  TITLE     "):
            title = next_line[12:]
            reference_loop_counter += 1
            if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
            else:
                break
            while (next_line.startswith("            ")) :
                title = "%s %s" % (title,next_line[12:])
                reference_loop_counter += 1
                if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                    next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
                else:
                    break
        elif next_line.startswith("  JOURNAL   "):
            journal = next_line[12:]
            reference_loop_counter += 1
            if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
            else:
                break
            while (next_line.startswith("            ")) :
                journal = "%s %s" % (journal,next_line[12:])
                reference_loop_counter += 1
                if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                    next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
                else:
                    break
        elif next_line.startswith("   PUBMED   "): 
            pubmed = next_line[12:] 
            reference_loop_counter += 1
            if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
            else:
                break
            while (next_line.startswith("            ")) : 
                pubmed = "%s %s" % (journal,next_line[12:]) 
                reference_loop_counter += 1
                if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines): 
                    next_line = metadata_lines[metadata_line_counter + reference_loop_counter] 
                else: 
                    break 
        elif next_line.startswith("  CONSRTM   "):
            consortium = next_line[12:]
            reference_loop_counter += 1
            if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines): 
                next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
            else:
                break 
            while (next_line.startswith("            ")) : 
                consortium = "%s %s" % (journal,next_line[12:]) 
                reference_loop_counter += 1
                if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                    next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
                else:
                    break
        else:
            reference_loop_counter += 1
            if ((metadata_line_counter + reference_loop_counter)<= num_metadata_lines):
                next_line = metadata_lines[metadata_line_counter + reference_loop_counter]
            else:
                break
    #Done grabbing reference lines, time to build the reference object.

    pubmed_link = ''
    publication_source = ''
    publication_date = ''
    if pubmed != '':
        publication_source = "PubMed"
    elif consortium != '':
        publication_source = consortium
    try:
        pubmed = int(pubmed)
    except ValueError:
        pubmed = 0
    if pubmed != 0:
        pubmed_link = "http://www.ncbi.nlm.nih.gov/pubmed/%s" % str(pubmed)
    if journal != '':
        potential_date_regex = r'(?<=\().+?(?=\))'
        potential_dates = re.findall(potential_date_regex, journal)
        
        for potential_date in reversed(potential_dates):                        
            try:
                record_time = datetime.datetime.strptime(potential_date, '%d-%b-%Y')
                if now_date > record_time:
                    publication_date = potential_date
                    break
            except ValueError:
                try:
                    record_time = datetime.datetime.strptime(potential_date, '%b-%Y')
                    if now_date > record_time:
                        publication_date = potential_date
                        break       
                except ValueError:
                    try:
                        record_time = datetime.datetime.strptime(potential_date, '%Y')
                        if now_date > record_time:
                            publication_date = potential_date
                            break
                    except ValueError:
                        next
    publication = [pubmed,publication_source,title,pubmed_link,publication_date,authors,journal]
    genome_publication_dict[publication_key] = publication
    #END OF PUBLICATION SECTION



def _create_feature_object(feature_text, complement_len, join_len, order_len, contig_length,
                         accession, sequence_part, source, exclude_ontologies, ontology_sources,
                         time_string, genetic_code, generate_ids_if_needed, 
                         # Output part:
                         report, feature_ids, feature_type_counts, feature_type_id_counter_dict,
                         ontology_terms_not_found):
            feature_object = dict()
            #split the feature into the key value pairs. "/" denotes start of a new key value pair.
            feature_key_value_pairs_list = feature_text.split("                     /")
            feature_header = feature_key_value_pairs_list.pop(0)
            if len(feature_header[:5].strip()) != 0:
                return None
            coordinates_info = feature_header[21:] 
            feature_type = feature_header[:21] 
            feature_type = feature_type.strip().replace(" ","_")
            if feature_type not in ['CDS','gene', 'mRNA']:
                #skip non core feature types.
                return None
            feature_object["type"] = feature_type

            quality_warnings = list() #list of warnings about the feature. Can do more with this at a later time.
            feature_keys_present_dict = dict() #dict of keys present in the feature

            #Get feature key value pairs
            for feature_key_value_pair in feature_key_value_pairs_list: 
                #the key value pair removing unnecessary white space (including new lines as these often span multiple lines)
                temp_string = re.sub( '\s+', ' ', feature_key_value_pair ).strip() 
                try: 
                    key, value = temp_string.split('=', 1) 
                except Exception, e: 
                    #Does not follow key value pair structure.  This unexpected. Skipping.
                    key = temp_string
                    value = ""

                value = re.sub(r'^"|"$', '', value.strip())
                feature_keys_present_dict[key.strip()] = 1

            coordinates_info = re.sub( '\s+', '', coordinates_info ).strip()
            original_coordinates = coordinates_info
            coordinates_list = list()
            apply_complement_to_all = False
            need_to_reverse_locations = False
            has_odd_coordinates = False
            can_not_process_feature = False
            if coordinates_info.startswith("complement") and coordinates_info.endswith(")"): 
                apply_complement_to_all = True
                need_to_reverse_locations = True
                coordinates_info = coordinates_info[complement_len:-1]
            if coordinates_info.startswith("join") and coordinates_info.endswith(")"):
                coordinates_info = coordinates_info[join_len:-1]
            if coordinates_info.startswith("order") and coordinates_info.endswith(")"):
                coordinates_info = coordinates_info[order_len:-1]
                has_odd_coordinates = True
                temp_warning = "Feature with the text %s has the rare 'order' coordinate. The sequence was joined together because KBase does not allow for a non contiguous resulting sequence with multiple locations for a feature.\n\n" % (feature_text)
#                quality_warnings.append(temp_warning)
                report.write(temp_warning)
                #annotation_metadata_warnings.append(temp_warning)
#                sql_cursor.execute("insert into annotation_metadata_warnings values(:warning)",(temp_warning,))
            coordinates_list = coordinates_info.split(",")
            
            [locations, dna_sequence_length, dna_sequence,
             can_not_process_feature] = _load_feature_locations(coordinates_list, complement_len, 
                                                                feature_text, contig_length, 
                                                                accession, sequence_part, 
                                                                apply_complement_to_all, 
                                                                can_not_process_feature, report)

            if has_odd_coordinates:
                    quality_warnings.insert(0,"Note this feature contains some atypical coordinates, see the rest of the warnings for details : %s" % (original_coordinates))
            if can_not_process_feature: 
                #skip source feature types.
                return None
            
            dna_sequence = dna_sequence.upper()

            if len(locations) > 0:
                if need_to_reverse_locations and (len(locations) > 1):
                    locations.reverse()
            feature_object["location"]=locations

            feature_object["dna_sequence_length"] = dna_sequence_length
            feature_object["dna_sequence"] = dna_sequence
            try:
                feature_object["md5"] = hashlib.md5(dna_sequence).hexdigest() 
            except Exception, e:
#                print "THE FEATURE TEXT IS : %s" % (feature_text)
#                print "THE FEATURE SEQUENCE IS : %s : " % (dna_sequence)
#                print "Help %s" % help(dna_sequence)
                raise Exception(e)

            [alias_dict, feature_id, product, pseudo_non_gene, has_protein_id, 
             ontology_terms, gene_feature_id, gene_feature_id2, transcript_id, 
             feature_id2] = _load_feature_properties(
                    feature_key_value_pairs_list, feature_type, source, exclude_ontologies, 
                    ontology_sources, time_string, 
                    # Output part:
                    feature_object, quality_warnings, feature_ids, ontology_terms_not_found)

            if feature_type == 'mRNA' or feature_type == 'CDS':
                if gene_feature_id:
                    feature_object['parent_gene'] = gene_feature_id
                if gene_feature_id2:
                    feature_object['parent_gene2'] = gene_feature_id2
                if product:
                    feature_object['product'] = product
                if feature_type == 'CDS' and transcript_id:
                    feature_object['transcript_id'] = transcript_id
            
            if feature_type == 'gene' and feature_id2:  # Alternative potential gene ID
                feature_object['id2'] = feature_id2

#            if len(additional_properties) > 0:
#                feature_object["additional_properties"] = additional_properties
#            if len(notes) > 0:
#                feature_object["notes"] = notes
#            if len(inference) > 0:
#                feature_object["inference"] = inference
            if len(alias_dict) > 0:
                feature_object["aliases"] = alias_dict.keys()
            if ("function" not in feature_object) and (product is not None):
                feature_object["function"] = product

            if feature_type == 'CDS':
                #GET TRANSLATION OF THE CDS.  IF THE GENBANK FILE DOES NOT HAVE IT.  
                coding_dna = Seq(feature_object["dna_sequence"], generic_dna)
                aa_seq = coding_dna.translate(table=genetic_code, to_stop=True)
                aa_trans_seq = str(aa_seq[0:].upper())

                if "protein_translation" in feature_object:
                    if aa_trans_seq != feature_object["protein_translation"].upper():
                        temp_warning = "%s translated amino acid sequence does not match the supplied amino acid sequence.\n\n" % (feature_id) 
                        report.write(temp_warning)
#                        quality_warnings.append(temp_warning) 
#                        sql_cursor.execute("insert into annotation_metadata_warnings values(:warning)",(temp_warning,)) 
                else:
                    if "dna_sequence" in feature_object:
                        feature_object["protein_translation"] = aa_trans_seq
                        feature_object["protein_translation_length"] = len(aa_trans_seq)
            
            if pseudo_non_gene:
                if feature_type == "CDS" and has_protein_id:
                    report.write("Feature text : {} is a CDS with pseudo and protein_id.\n\n".format(feature_text))
                    #don not include this feature.
                return None

            if feature_object["type"] in feature_type_counts:
                feature_type_counts[feature_object["type"]] += 1
            else:
                feature_type_counts[feature_object["type"]] = 1     

            if feature_id is None:
                if generate_ids_if_needed == 1:
                    #MAKE AUTOGENERATED ID
                    #MAKING ALL IDS UNIQUE ACROSS THE GENOME.
                    if feature_object["type"] not in feature_type_id_counter_dict:
                        feature_type_id_counter_dict[feature_object["type"]] = 1;
                        feature_id = "%s_%s" % (feature_object["type"],str(1)) 
                    else: 
                        feature_type_id_counter_dict[feature_object["type"]] += 1; 
                        feature_id = "%s_%s" % (feature_type,str(feature_type_id_counter_dict[feature_object["type"]]))
                else:
                    #Throw an error informing user they can set the generate ids if needed checkbox
                    #do specific errors so they know where we look for the ids.
                    raise Exception("There was no feature specific id for {}.  \
For gene type we take the id from the locus tag \
(except for Ensembl, then the gene field)\
For CDS type we take the id from the protein id field. \
NOTE IF YOU WANT THIS STILL UPLOADED GO TO THE \
ADVANCED OPTIONS AND CHECK THE\
\"Generate IDs if needed\" checkbox".format(feature_text))

#            feature_object["quality_warnings"] = quality_warnings

#            ############################################
#            #DETERMINE ID TO USE FOR THE FEATURE OBJECT
#            ############################################
#            if feature_type not in features_type_containers_dict:
#                features_type_containers_dict[feature_type] = dict()
#            feature_id = None

#OLD WAY TRIED TO USE ID FROM THE FEATURE, UNIQUENESS ONLY GUARANTEED WITH FEATURE CONTAINER AND NOT ACROSS THE GENOME ANNOTATION
#            if "feature_specific_id" not in feature_object:
#                if "locus_tag" not in feature_object:
#                    if feature_type not in feature_type_id_counter_dict:
#                        feature_type_id_counter_dict[feature_type] = 1;
#                        feature_id = "%s_%s" % (feature_type,str(1))
#                    else:
#                        feature_type_id_counter_dict[feature_type] += 1;
#                        feature_id = "%s_%s" % (feature_type,str(feature_type_id_counter_dict[feature_type]))
#                else:
#                    feature_id = feature_object["locus_tag"]
#            else:
#                feature_id = feature_object["feature_specific_id"]
#            if feature_id in features_type_containers_dict[feature_type]:
#                #Insure that no duplicate ids exist
#                if feature_type not in feature_type_id_counter_dict:
#                    feature_type_id_counter_dict[feature_type] = 1;
#                    feature_id = "%s_%s" % (feature_type,str(1))
#                else: 
#                    feature_type_id_counter_dict[feature_type] += 1;
#                    feature_id = "%s_%s" % (feature_type,str(feature_type_id_counter_dict[feature_type]))
#END OLD WAY


##NEW WAY:  MAKING ALL IDS UNIQUE ACROSS THE GENOME.
#            if feature_type not in feature_type_id_counter_dict:
#                feature_type_id_counter_dict[feature_type] = 1;
#                feature_id = "%s_%s" % (feature_type,str(1))
#            else: 
#                feature_type_id_counter_dict[feature_type] += 1;
#                feature_id = "%s_%s" % (feature_type,str(feature_type_id_counter_dict[feature_type]))
##END NEW WAY
            if len(ontology_terms) > 0:
                feature_object["ontology_terms"]=ontology_terms
            feature_object["id"] = feature_id

            ########################################
            #CLEAN UP UNWANTED FEATURE KEYS
            #######################################
            if "locus_tag" in feature_object: 
                del feature_object["locus_tag"]
            if "gene" in feature_object: 
                del feature_object["gene"]
            if "feature_specific_id" in feature_object: 
                del feature_object["feature_specific_id"]

#            feature_object["quality_warnings"] = quality_warnings

            #MAKE ENTRY INTO THE FEATURE TABLE
#            pickled_feature = cPickle.dumps(feature_object, cPickle.HIGHEST_PROTOCOL) 
#            sql_cursor.execute("insert into features values(:feature_id, :feature_type , :sequence_length, :feature_data)", 
#                               (feature_id, feature_object["type"], feature_object["dna_sequence_length"], sqlite3.Binary(pickled_feature),))

            return feature_object



def _load_feature_locations(coordinates_list, complement_len, feature_text,
                            contig_length, accession, sequence_part,
                            apply_complement_to_all, can_not_process_feature,
                            report):
            last_coordinate = 0
            dna_sequence_length = 0
            dna_sequence = ''

            locations = list()#list of location objects
            for coordinates in coordinates_list:
                apply_complement_to_current = False
                if coordinates.startswith("complement") and coordinates.endswith(")"): 
                    apply_complement_to_current = True 
                    coordinates = coordinates[complement_len:-1]
                #Look for and handle odd coordinates
                if (("<" in coordinates) or (">" in coordinates)):
                    has_odd_coordinates = True
                    #temp_warning = "Feature with the text %s has a '<' or a '>' in the coordinates.  This means the feature starts or ends beyond the known sequence.\n\n" % (feature_text)
                    #quality_warnings.append(temp_warning)
                    #report.write(temp_warning)
                    #annotation_metadata_warnings.append(temp_warning)
#                    sql_cursor.execute("insert into annotation_metadata_warnings values(:warning)",(temp_warning,))
                    coordinates= re.sub('<', '', coordinates)
                    coordinates= re.sub('>', '', coordinates)

                period_count = coordinates.count('.')
                if ((period_count == 2) and (".." in coordinates)):
                    start_pos, end_pos = coordinates.split('..', 1)                    
                elif period_count == 0:
                    start_pos = coordinates
                    end_pos = coordinates
                elif period_count == 1:
                    start_pos, end_pos = coordinates.split('.', 1) 
                    has_odd_coordinates = True
                    temp_warning = "Feature with the text %s has a single period in the original coordinate this indicates that the exact location is unknown but that it is one of the bases between bases %s and %s, inclusive.  Note the entire sequence range has been put into this feature.\n\n" % (feature_text, str(start_pos),str(end_pos))
                    #quality_warnings.append(temp_warning)
                    report.write(temp_warning)
                    #annotation_metadata_warnings.append(temp_warning)
#                    sql_cursor.execute("insert into annotation_metadata_warnings values(:warning)",(temp_warning,))
                elif period_count > 2 :
                    can_not_process_feature = True
                else:
                    can_not_process_feature = True
                if "^" in coordinates:
                    start_pos, end_pos = coordinates.split('^', 1) 
                    has_odd_coordinates = True
                    temp_warning = "Feature with the text %s is between bases.  It points to a site between bases %s and %s, inclusive.  Note the entire sequence range has been put into this feature.\n\n" % (feature_text, str(start_pos),str(end_pos))
                    #quality_warnings.append(temp_warning)
                    report.write(temp_warning)
                    #annotation_metadata_warnings.append(temp_warning)       
#                    sql_cursor.execute("insert into annotation_metadata_warnings values(:warning)",(temp_warning,))

                if not can_not_process_feature:
                    if (represents_int(start_pos) and represents_int(end_pos)):
                        if int(start_pos) > int(end_pos):
                            print "FEATURE TEXT: " + feature_text
                            raise Exception("The genbank record %s has coordinates that are out of order. Start coordinate %s is bigger than End coordinate %s. Should be ascending order." % (accession, str(start_pos), str(end_pos)))

#CANT COUNT ON THEM BEING IN ASCENDING POSITIONAL ORDER
#                    if (int(start_pos) < last_coordinate or int(end_pos) < last_coordinate) and ("trans_splicing" not in feature_keys_present_dict) :
#                        fasta_file_handle.close()
#                        raise Exception("The genbank record %s has coordinates that are out of order. Start coordinate %s and/or End coordinate %s is larger than the previous coordinate %s within this feature. Should be ascending order since this is not a trans_splicing feature." % (accession, str(start_pos), str(end_pos),str(last_coordinate)))

                        if (int(start_pos) > contig_length) or (int(end_pos) > contig_length):
                            raise Exception("The genbank record %s has coordinates (start: %s , end: %s) that are longer than the sequence length %s." % \
                                            (accession,str(start_pos), int(end_pos),str(contig_length)))

                        segment_length = (int(end_pos) - int(start_pos)) + 1
                        dna_sequence_length += segment_length
                        temp_sequence = sequence_part[(int(start_pos)-1):int(end_pos)] 
                        strand = "+"
                        location_start = int(start_pos)
                        if apply_complement_to_current or apply_complement_to_all: 
                            my_dna = Seq(temp_sequence, IUPAC.ambiguous_dna)
                            my_dna = my_dna.reverse_complement()
                            temp_sequence = str(my_dna).upper()      
                            strand = "-"
                            location_start = location_start + (segment_length - 1)
                        if apply_complement_to_all:
                            dna_sequence =  temp_sequence + dna_sequence 
                        else:
                            dna_sequence +=  temp_sequence 

                        locations.append([accession,location_start,strand,segment_length]) 
                    else:
                        #no valid coordinates
                        print "Feature text : {} :".format(feature_text)
                        raise Exception("The genbank record %s contains coordinates that are not valid number(s).  Feature text is : %s" % (accession,feature_text)) 

                    last_coordinate = int(end_pos)
            return [locations, dna_sequence_length, dna_sequence, can_not_process_feature]



def _load_feature_properties(feature_key_value_pairs_list, feature_type, source,
                             exclude_ontologies, ontology_sources, time_string,
                             # Output part:
                             feature_object, quality_warnings, feature_ids,
                             ontology_terms_not_found):
            #Need to determine id for the feature : order selected by gene, then locus.
            alias_dict = dict() #contains locus_tag, gene, gene_synonym, dbxref, then value is 1 (old way value is a list of sources).
            inference = ""
            notes = ""
            additional_properties = dict()
            feature_specific_id = None
            feature_id = None
            product = None
            EC_number = None
            pseudo_non_gene = False
            has_protein_id = False
            ontology_terms = dict()
            feature_id2 = None        # This is optional gene ID (defined based in "gene" property)
            gene_feature_id = None    # This is feature_id of parent gene for current CDS feature
            gene_feature_id2 = None   # This is optional feature_id of parent gene for current CDS feature
            transcript_id = None      # This is optional reference from CDS to mRNA

            for feature_key_value_pair in feature_key_value_pairs_list:
                #the key value pair removing unnecessary white space (including new lines as these often span multiple lines)
                temp_string = re.sub( '\s+', ' ', feature_key_value_pair ).strip()

                try: 
                    key, value = temp_string.split('=', 1) 
                except Exception, e: 
                    #Does not follow key value pair structure.  This unexpected. Skipping.
                    if temp_string == "pseudo":
                        if feature_type == "gene":
                            feature_object["type"] = "pseudogene"
                        else:
                            pseudo_non_gene = True
                    elif temp_string != "trans_splicing":
                        temp_warning = "%s has the following feature property does not follow the expected key=value format : %s" % (feature_id, temp_string) 
                        quality_warnings.append(temp_warning)
                        #annotation_metadata_warnings.append(temp_warning)
#                        sql_cursor.execute("insert into annotation_metadata_warnings values(:warning)",(temp_warning,))       
                    key = temp_string 
                    value = "" 

                key = key.strip()
                value = re.sub(r'^"|"$', '', value.strip())

                if key == "gene":
                    feature_object["gene"] = value 
                    alias_dict[value]=1 
                    if source.upper() == "ENSEMBL":
                        if feature_type == "gene":
                            if value in feature_ids:
                                raise Exception("More than one feature has the specific feature id of {}.  All feature ids need to be unique.".format(value))
                            else:
                                feature_id = value
                                feature_ids[value] = 1
                        elif feature_type == "CDS" or feature_type == "mRNA":
                            gene_feature_id = value
                    else:
                        if feature_type == "gene":
                            feature_id2 = value
                        elif feature_type == "CDS" or feature_type == "mRNA":
                            gene_feature_id2 = value
#Kept lines, for dealing with aliases if keeping track of sources/source field
#                    if value in alias_dict and ("Genbank Gene" not in alias_dict[value]) :
#                        alias_dict[value].append("Genbank Gene")
#                    else:
#                        alias_dict[value]=["Genbank Gene"] 
                elif key == "locus_tag":
                    feature_object["locus_tag"] = value 
                    alias_dict[value]=1 
                    if source.upper() != "ENSEMBL":
                        if feature_type == "gene":
                            if value in feature_ids:
                                raise Exception("More than one feature has the specific feature id of {}.  All feature ids need to be unique.".format(value))
                            else:
                                feature_id = value
                                feature_ids[value] = 1
                        elif feature_type == "CDS" or feature_type == "mRNA":
                            gene_feature_id = value
#                    if feature_type == "gene":
#                        feature_object["feature_specific_id"] = value
                elif key == "old_locus_tag" or key == "standard_name" or key == "EC_number":
                    alias_dict[value]=1 
                elif key == "gene_synonym":
                    synonyms = value.split(';') 
                    for i in synonyms:
                        i = i.strip()
                        alias_dict[i]=1 
                elif (key == "transcript_id"):
#                    if feature_type == "mRNA":
#                        feature_object["feature_specific_id"] = value 
                    if feature_type == "mRNA":
                        feature_id = value
                    elif feature_type == "CDS":
                        transcript_id = value
                    alias_dict[value]=1 
                elif (key == "protein_id"):
#                    if feature_type == "CDS":
#                        feature_object["feature_specific_id"] = value
                    if feature_type == "CDS":
                        feature_id = value
#                         if value in feature_ids:
#                             raise Exception("More than one feature has the specific feature id of {}.  All feature ids need to be unique.".format(value))
#                         else:
#                             feature_id = value
#                             feature_ids[value] = 1 
                    alias_dict[value]=1 
                    has_protein_id = True

                elif (key == "db_xref"):
                    try:
                        db_xref_source, db_xref_value = value.strip().split(':',1)
                        db_xref_value = db_xref_value.strip()
                        db_xref_source = db_xref_source.strip()
                        if db_xref_source.upper() == "GO" or db_xref_source.upper() == "PO":
                            if exclude_ontologies == 0:
                                ontology_id=value.strip()
                                ontology_source = db_xref_source.upper()
                                if ontology_source == "GO":
                                    ontology_ref = "KBaseOntology/gene_ontology"
                                elif ontology_source == "PO":
                                    ontology_ref = "KBaseOntology/plant_ontology"
                                if ontology_id not in ontology_sources[ontology_source]:
#                                alias_dict[value]=1 
    #                                print ("Term {} was not found in our ontology database. It is likely a deprecated term.".format(ontology_id))
                                    if ontology_id not in ontology_terms_not_found:
                                        ontology_terms_not_found[ontology_id] = 1
                                    else:
                                        ontology_terms_not_found[ontology_id] = ontology_terms_not_found[ontology_id] + 1
                                else:
                                    if(ontology_source not in ontology_terms):
                                        ontology_terms[ontology_source]=dict()
                                    if( ontology_id not in ontology_terms[ontology_source]):
                                        OntologyEvidence=[{"method":"KBase_Genbank_uploader from db_xref field","timestamp":time_string,"method_version":"1.0"}]
                                        OntologyData={"id":ontology_id,"ontology_ref":ontology_ref,
                                                      "term_name":ontology_sources[ontology_source][ontology_id]["name"],
                                                      "term_lineage":[],"evidence":OntologyEvidence}
                                        ontology_terms[ontology_source][ontology_id]=OntologyData
                        else:
                            alias_dict[value]=1 
                    except Exception, e: 
                        alias_dict[value]=1 
#                        db_xref_source = "Unknown"
#                        db_xref_value = value.strip()
#                    if db_xref_value.strip() in alias_dict: 
#                        if (db_xref_source.strip() not in alias_dict[db_xref_value.strip()]) :
#                            alias_dict[db_xref_value.strip()].append(db_xref_source.strip())
#                    else:
#                        alias_dict[db_xref_value.strip()]=[db_xref_source.strip()]
#                elif (key == "note"):
#                    if notes != "":
#                        notes += ";"
#                    notes += value
                elif (key == "translation"):
                    #
                    # TODO
                    #NOTE THIS IS A PLACE WHERE A QUALITY WARNING CHECK CAN BE DONE, 
                    #see if translation is accurate.(codon start (1,2,3) may need to be used)
                    #
                    value = re.sub('\s+','',value)
                    feature_object["protein_translation"] = value
                    feature_object["protein_translation_length"] = len(value)
                elif ((key == "function") and (value is not None) and (value.strip() == "")) :
                    feature_object["function"] = value
                elif (key == "product"):
                    product = value
#                    additional_properties[key] = value
#                elif (key == "trans_splicing"):
#                    feature_object["trans_splicing"] = 1
#                elif (key == "EC_number") and feature_type == "CDS":
#                    EC_number = value
#                else:
#                    if key in additional_properties:
#                        additional_properties[key] =  "%s::%s" % (additional_properties[key],value)
#                    else:
#                        additional_properties[key] = value
            
            if feature_type == 'gene' and (not feature_id) and feature_id2:
                if feature_id2 not in feature_ids:
                    feature_id = feature_id2
                    feature_ids[feature_id2] = 1

            return [alias_dict, feature_id, product, pseudo_non_gene, has_protein_id, 
                    ontology_terms, gene_feature_id, gene_feature_id2, transcript_id, feature_id2]






# called only if script is run from command line
if __name__ == "__main__":
    script_details = script_utils.parse_docs(upload_genome.__doc__)    

    import argparse

    parser = argparse.ArgumentParser(prog=__file__, 
                                     description=script_details["Description"],
                                     epilog=script_details["Authors"])
                                     
    parser.add_argument('--shock_service_url', 
                        help=script_details["Args"]["shock_service_url"],
                        action='store', type=str, nargs='?', required=True)
    parser.add_argument('--handle_service_url', 
                        action='store', type=str, nargs='?', default=None, required=True)
    parser.add_argument('--workspace_name', nargs='?', help='workspace name to populate', required=True)
    parser.add_argument('--taxon_wsname', nargs='?', help='workspace name with taxon in it, assumes the same workspace_service_url', required=False, default='ReferenceTaxons')
#    parser.add_argument('--taxon_names_file', nargs='?', help='file with scientific name to taxon id mapping information in it.', required=False, default="/homes/oakland/jkbaumohl/Genome_Spec_files/Taxonomy/names.dmp")
    parser.add_argument('--taxon_reference', nargs='?', help='ONLY NEEDED IF PERSON IS DOING A CUSTOM TAXON NOT REPRESENTED IN THE NCBI TAXONOMY TREE', required=False)
    parser.add_argument('--workspace_service_url', action='store', type=str, nargs='?', required=True) 

    parser.add_argument('--object_name', 
                        help="genbank file", 
                        nargs='?', required=False)
    parser.add_argument('--source', 
                        help="data source : examples Refseq, Genbank, Pythozyme, Gramene, etc", 
                        nargs='?', required=False, default="Genbank") 
    parser.add_argument('--type', 
                        help="data source : examples Reference, Representative, User Upload", 
                        nargs='?', required=False, default="User upload") 
    parser.add_argument('--release', 
                        help="Release or version of the data.  Example Ensembl release 30", 
                        nargs='?', required=False) 
    parser.add_argument('--genetic_code', 
                        help="genetic code for the genome, normally determined by taxon information. Will override taxon supplied genetic code if supplied. Defaults to 1", 
                        nargs='?', type=int, required=False)
    parser.add_argument('--generate_ids_if_needed', 
                        help="If the fields used for ID determination are not present the uploader will fail by default. If generate_ids_id_needed is 1 then it will generate IDs (Feature_AutoincrementNumber format)", 
                        nargs='?', type=int, required=False)
    parser.add_argument('--exclude_ontologies', 
                        help="Some larger genomes may not fit in the 1 GB limit, one way to increase likelihood they will fit is to exclude the ontologies.", 
                        nargs='?', type=int, required=False)
    parser.add_argument('--input_directory', 
                        help="directory the genbank file is in", 
                        action='store', type=str, nargs='?', required=True)

    args, unknown = parser.parse_known_args()

    logger = script_utils.stderrlogger(__file__)

    logger.debug(args)

    try:
        obj_name = upload_genome(shock_service_url = args.shock_service_url,
                                 handle_service_url = args.handle_service_url, 
                                 input_directory = args.input_directory, 
                                 workspace_name = args.workspace_name,
                                 workspace_service_url = args.workspace_service_url,
                                 taxon_wsname = args.taxon_wsname,
                                 taxon_reference = args.taxon_reference,
                                 core_genome_name = args.object_name,
                                 source = args.source,
                                 release = args.release,
                                 type = args.type,
                                 genetic_code = args.genetic_code,
                                 generate_ids_if_needed = args.generate_ids_if_needed,
                                 logger = logger)
    except Exception, e:
        logger.exception(e)
        sys.exit(1)

    sys.exit(0)


