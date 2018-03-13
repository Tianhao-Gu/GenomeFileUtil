import os
import sys
import shutil
import uuid
import time
import json
import gzip
import hashlib
import collections
import datetime
import re
import copy

# KBase imports
from DataFileUtil.DataFileUtilClient import DataFileUtil
from AssemblyUtil.AssemblyUtilClient import AssemblyUtil
from GenomeUtils import warnings, propagate_cds_props_to_gene
from GenomeInterface import GenomeInterface

# 3rd party imports
from Bio.Data import CodonTable
from Bio.Data.CodonTable import TranslationError
import Bio.SeqIO
from Bio.Seq import Seq

codon_table = CodonTable.ambiguous_generic_by_name["Standard"]

def log(message, prefix_newline=False):
    """Logging function, provides a hook to suppress or redirect log messages."""
    print(('\n' if prefix_newline else '') + '{0:.2f}'.format(time.time()) + ': ' + str(message))


class FastaGFFToGenome:

    def __init__(self, config):
        self.cfg = config
        self.au = AssemblyUtil(config.callbackURL)
        self.dfu = DataFileUtil(self.cfg.callbackURL)
        self.gi = GenomeInterface(self.cfg)
        self.taxon_wsname = self.cfg.raw['taxon-workspace-name']
        self.time_string = str(datetime.datetime.fromtimestamp(
            time.time()).strftime('%Y_%m_%d_%H_%M_%S'))
        yml_text = open('/kb/module/kbase.yml').read()
        self.version = re.search("module-version:\n\W+(.+)\n", yml_text
                                 ).group(1)
        self.code_table = 11
        self.aliases = ()
        self.is_phytozome = False
        self.strict = True
        self.generate_genes = False
        self.warnings = []
        self.feature_dict = {}
        self.cdss = set()
        self.ontologies_present = collections.defaultdict(dict)
        self.skiped_features = collections.Counter()
        self.feature_counts = collections.Counter()

    def warn(self, message):
        self.warnings.append(message)
        print message

    def import_file(self, params):

        # 1) validate parameters
        self._validate_import_file_params(params)
        self.code_table = params.get('genetic_code', 11)

        # 2) construct the input directory staging area
        input_directory = os.path.join(self.cfg.sharedFolder, 'fast_gff_upload_'+str(uuid.uuid4()))
        os.makedirs(input_directory)
        file_paths = self._stage_input(params, input_directory)

        # 3) extract out the parameters
        params = self._set_parsed_params(params)
        if params.get('generate_missing_genes'):
            self.generate_genes = True

        # 4) do the upload
        result = self.upload_genome(
            input_fasta_file=file_paths["fasta_file"],
            input_gff_file=file_paths["gff_file"],
            workspace_name=params['workspace_name'],
            core_genome_name=params['genome_name'],
            scientific_name=params['scientific_name'],
            source=params['source'],
            genome_type=params['type'],
            release=params['release'],
            metadata=params['metadata']
        )

        # 5) clear the temp directory
        shutil.rmtree(input_directory)

        # 6) return the result
        info = result['genome_info']
        details = {
            'genome_ref': str(info[6]) + '/' + str(info[0]) + '/' + str(info[4]),
            'genome_info': info
        }

        return details

    def upload_genome(self, input_gff_file=None, input_fasta_file=None,
                      workspace_name=None, core_genome_name=None,
                      scientific_name="unknown_taxon", source=None,
                      release=None, genome_type=None, metadata=None):

        # save assembly file
        assembly_ref = self.au.save_assembly_from_fasta(
            {'file': {'path': input_fasta_file},
             'workspace_name': workspace_name,
             'assembly_name': core_genome_name + ".assembly"})
        assembly_data = self.dfu.get_objects(
            {'object_refs': [assembly_ref],
             'ignore_errors': 0})['data'][0]['data']

        # reading in GFF file
        features_by_contig = self._retrieve_gff_file(input_gff_file)
        contig_ids = set(assembly_data['contigs'])
        for cid in set(features_by_contig.keys()) - contig_ids:
            self.warn("Sequence name {} does not match a sequence id in the "
                      "FASTA file. {} features will not be imported."
                      .format(cid, len(features_by_contig[cid])))
            if self.strict:
                raise ValueError("Features must match fasta sequence")

        # parse feature information
        fasta_contigs = Bio.SeqIO.parse(input_fasta_file, "fasta")
        for contig in fasta_contigs:
            molecule_type = str(contig.seq.alphabet).replace(
                'IUPACAmbiguous', '').strip('()')
            for feature in features_by_contig.get(contig.id, []):
                self._transform_feature(contig, feature)
        self._process_cdss()

        # generate genome info
        genome = self._gen_genome_info(core_genome_name, scientific_name,
                                       assembly_ref, source, assembly_data,
                                       input_gff_file, molecule_type)
        genome['release'] = release
        genome['type'] = genome_type

        json.dump(genome, open("{}/{}.json".format(self.cfg.sharedFolder,
                                                   genome['id']), 'w'), indent=4)
        result = self.gi.save_one_genome({
            'workspace': workspace_name,
            'name': core_genome_name,
            'data': genome,
            "meta": metadata,
        })
        report_string = 'A genome with {} contigs and the following feature ' \
                        'types was imported: {}'.format(len(
            genome['contig_ids']), "\n".join([k+": "+str(v) for k, v in
                                              genome['feature_counts'].items()]))
        print report_string

        return {'genome_info': result['info'], 'report_string': report_string}

    @staticmethod
    def _location(in_feature):
        in_feature['strand'] = in_feature['strand'].replace("-1", "-").replace(
            "1", "+")
        if in_feature['strand'] == '+':
            start = in_feature['start']
        elif in_feature['strand'] == '-':
            start = in_feature['end']
        else:
            raise ValueError('Invalid feature strand: {}'
                             .format(in_feature['strand']))
        return [
            in_feature['contig'],
            start,
            in_feature['strand'],
            in_feature['end'] - in_feature['start'] + 1
        ]

    def _get_ontology(self, feature):
        ontology = collections.defaultdict(dict)
        for key in ("GO_process", "GO_function", "GO_component"):
            if key in feature['attributes']:
                sp = feature['attributes'][key][0][3:].split(" - ")
                ontology['GO'][sp[0]] = [1]
                self.ontologies_present['GO'][sp[0]] = sp[1]
        # TODO: Support other ontologies
        return dict(ontology)

    @staticmethod
    def _validate_import_file_params(params):
        """
        validate_import_file_params:
                    validates params passed to FastaGFFToGenome.import_file method

        """

        # check for required parameters
        for p in ['workspace_name', 'genome_name', 'fasta_file', 'gff_file']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

        # one and only one of 'path', or 'shock_id' is required
        for key in ('fasta_file', 'gff_file'):
            file = params[key]
            if not isinstance(file, dict):
                raise ValueError('Required "{}" field must be a map/dict'.format(key))
            n_valid_fields = 0
            if 'path' in file and file['path'] is not None:
                n_valid_fields += 1
            if 'shock_id' in file and file['shock_id'] is not None:
                n_valid_fields += 1
            if 'ftp_url' in file and file['ftp_url'] is not None:
                n_valid_fields += 1
                raise ValueError('FTP link is currently not supported for FastaGFFToGenome')
            if n_valid_fields < 1:
                error_msg = 'Required "{}" field must include one source: '.format(key)
                error_msg += 'path | shock_id'
                raise ValueError(error_msg)
            if n_valid_fields > 1:
                error_msg = 'Required "{}" field has too many sources specified: '.format(key)
                error_msg += str(file.keys())
                raise ValueError(error_msg)

        # check for valid type param
        valid_types = ['Reference', 'User upload', 'Representative']
        if params.get('type') and params['type'] not in valid_types:
            error_msg = 'Entered value for type is not one of the valid entries of '
            error_msg += '[' + ''.join('"' + str(e) + '", ' for e in valid_types)[0: -2] + ']'
            raise ValueError(error_msg)

    def _set_parsed_params(self, params):
        log('Setting params')

        # default params
        default_params = {
            'taxon_wsname': self.cfg.raw['taxon-workspace-name'],
            'scientific_name': 'unknown_taxon',
            'taxon_reference': None,
            'source': 'User',
            'release': None,
            'type': 'User upload',
            'metadata': {}
        }

        for field in default_params:
            if field not in params:
                params[field] = default_params[field]

        log(json.dumps(params, indent=1))

        return params

    def _stage_input(self, params, input_directory):
        """
        stage_input: Setup the input_directory by fetching the files and uncompressing if needed

        """

        file_paths = dict()
        for key in ('fasta_file', 'gff_file'):
            file = params[key]
            file_path = None
            if 'path' in file and file['path'] is not None:
                local_file_path = file['path']
                file_path = os.path.join(input_directory, os.path.basename(local_file_path))
                log('Moving file from {} to {}'.format(local_file_path, file_path))
                shutil.copy2(local_file_path, file_path)

            if 'shock_id' in file and file['shock_id'] is not None:
                # handle shock file
                log('Downloading file from SHOCK node: {}-{}'.format(
                                                        self.cfg.sharedFolder, file['shock_id']))
                sys.stdout.flush()
                file_name = self.dfu.shock_to_file({'file_path': input_directory,
                                                    'shock_id': file['shock_id']
                                                    })['node_file_name']
                file_path = os.path.join(input_directory, file_name)

            # extract the file if it is compressed
            if file_path is not None:
                print("staged input file =" + file_path)
                sys.stdout.flush()
                dfUtil_result = self.dfu.unpack_file({'file_path': file_path})
                file_paths[key] = dfUtil_result['file_path']
            else:
                raise ValueError('No valid files could be extracted based on the input')

        return file_paths

    def _retrieve_gff_file(self, input_gff_file):
        """
        _retrieve_gff_file: retrieve info from gff_file
    
        """
        log("Reading GFF file")
    
        feature_list = collections.defaultdict(list)
        is_patric = 0

        gff_file_handle = open(input_gff_file, 'rb')
        current_line = gff_file_handle.readline()
        line_count = 0

        while (current_line != ''):
            current_line = current_line.strip()

            if(current_line.isspace() or current_line == "" or current_line.startswith("#")):
                pass
            else:
                #Split line
                (contig_id, source_id, feature_type, start, end,
                 score, strand, phase, attributes) = current_line.split('\t')

                #Checking to see if Phytozome
                if "phytozome" in source_id.lower():
                    self.is_phytozome = True

                #Checking to see if Phytozome
                if "PATRIC" in source_id:
                    is_patric = True

                #PATRIC prepends their contig ids with some gibberish
                if is_patric and "|" in contig_id:
                    contig_id = contig_id.split("|", 1)[1]

                #Populating basic feature object
                ftr = {'contig': contig_id, 'source': source_id,
                       'type': feature_type, 'start': int(start),
                       'end': int(end), 'score': score, 'strand': strand,
                       'phase': phase, 'attributes': collections.defaultdict(list)}

                #Populating with attribute key-value pair
                #This is where the feature id is from
                for attribute in attributes.split(";"):
                    attribute = attribute.strip()

                    #Sometimes empty string
                    if not attribute:
                        continue

                    #Use of 1 to limit split as '=' character can also be made available later
                    #Sometimes lack of "=", assume spaces instead
                    if("=" in attribute):
                        key, value = attribute.split("=", 1)
                        ftr['attributes'][key].append(value.strip('"'))
                    elif(" " in attribute):
                        key, value = attribute.split(" ", 1)
                        ftr['attributes'][key].append(value.strip('"'))
                    else:
                        log("Warning: attribute "+attribute+" cannot be separated into key,value pair")

                ftr['attributes']['raw'] = attributes
                if "ID" in ftr['attributes']:
                    ftr['ID'] = ftr['attributes']['ID'][0]
                if "Parent" in ftr['attributes']:
                    ftr['Parent'] = ftr['attributes']['Parent'][0]

                feature_list[contig_id].append(ftr)

            current_line = gff_file_handle.readline()

        gff_file_handle.close()

        #Some GFF/GTF files don't use "ID" so we go through the possibilities        
        feature_list = self._add_missing_identifiers(feature_list)

        #Most bacterial files have only CDSs
        #In order to work with prokaryotic and eukaryotic gene structure synonymously
        #Here we add feature dictionaries representing the parent gene and mRNAs
        #feature_list = self._add_missing_parents(feature_list)

        #Phytozome has the annoying habit of editing their identifiers so we fix them
        if self.is_phytozome:
            self._update_phytozome_features(feature_list)

        #All identifiers need to be checked so that they follow the same general rules
        #Rules are listed within the function itself
        feature_list = self._update_identifiers(feature_list)

        return feature_list

    @staticmethod
    def _add_missing_identifiers(feature_list):
        print("Adding missing identifiers")
        #General rule is to iterate through a range of possibilities if "ID" is missing
        for contig in feature_list.keys():
            for i in range(len(feature_list[contig])):
                if "ID" not in feature_list[contig][i]:
                    for key in ("transcriptId", "proteinId", "PACid",
                                "pacid", "Parent", "name",):
                        if key in feature_list[contig][i]['attributes']:
                            feature_list[contig][i]['ID'] = feature_list[
                                contig][i]['attributes'][key][0]
                            break

                    #If the process fails, throw an error
                    if "ID" not in feature_list[contig][i]:
                            log("Error: Cannot find unique ID to utilize in "
                                "GFF attributes: {}.{}.{}:{}".format(
                                    feature_list[contig][i]['contig'],
                                    feature_list[contig][i]['source'],
                                    feature_list[contig][i]['type'],
                                    str(feature_list[contig][i]['attributes']))
                                )
        return feature_list

    @staticmethod
    def _add_missing_parents(feature_list):

        #General rules is if CDS or RNA missing parent, add them
        for contig in feature_list.keys():
            ftrs = feature_list[contig]
            new_ftrs = []
            for i in range(len(ftrs)):
                if("Parent" not in ftrs[i]):
                    #Assuming parent doesn't exist at all, so create de novo instead of trying to find it
                    if("RNA" in ftrs[i]["type"] or "CDS" in ftrs[i]["type"]):
                        new_gene_ftr = copy.deepcopy(ftrs[i])
                        new_gene_ftr["type"] = "gene"
                        ftrs[i]["Parent"]=new_gene_ftr["ID"]
                        new_ftrs.append(new_gene_ftr)

                    if("CDS" in ftrs[i]["type"]):
                        new_rna_ftr = copy.deepcopy(ftrs[i])
                        new_rna_ftr["type"] = "mRNA"
                        new_ftrs.append(new_rna_ftr)
                        ftrs[i]["Parent"]=new_rna_ftr["ID"]

                new_ftrs.append(ftrs[i])
            feature_list[contig]=new_ftrs
        return feature_list

    @staticmethod
    def _update_phytozome_features(feature_list):

        #General rule is to use the "Name" field where possible
        #And update parent attribute correspondingly
        for contig in feature_list.keys():
            feature_position_dict = {}
            for i in range(len(feature_list[contig])):

                #Maintain old_id for reference
                #Sometimes ID isn't available, so use PACid
                old_id = None
                for key in ("ID", "PACid", "pacid"):
                    if(key in feature_list[contig][i]):
                        old_id = feature_list[contig][i][key]
                        break
                if(old_id is None):
                    #This should be an error
                    print ("Cannot find unique ID, PACid, or pacid in GFF "
                           "attributes: " + feature_list[contig][i][contig])
                    continue

                #Retain old_id
                feature_position_dict[old_id]=i

                # Clip off the increment on CDS IDs so fragments of the same
                # CDS share the same ID
                if "CDS" in feature_list[contig][i]["ID"]:
                    feature_list[contig][i]["ID"] = feature_list[contig][i]["ID"].rsplit('.', 1)[0]

                #In Phytozome, gene and mRNA have "Name" field, CDS do not
                if("Name" in feature_list[contig][i]):
                    feature_list[contig][i]["ID"] = feature_list[contig][i]["Name"]

                if("Parent" in feature_list[contig][i]):
                    #Update Parent to match new ID of parent ftr
                    feature_list[contig][i]["Parent"] = feature_list[contig][feature_position_dict[feature_list[contig][i]["Parent"]]]["ID"]

        return feature_list

    @staticmethod
    def _update_identifiers(feature_list):

        #General rules:
        #1) Genes keep identifier
        #2) RNAs keep identifier only if its different from gene, otherwise append ".mRNA"
        #3) CDS always uses RNA identifier with ".CDS" appended

        CDS_count_dict = dict()
        mRNA_parent_dict = dict()

        for contig in feature_list.keys():
            for ftr in feature_list[contig]:
                if("Parent" in ftr):

                    #Retain old_id of parents
                    old_id = ftr["ID"]

                    if(ftr["ID"] == ftr["Parent"] or "CDS" in ftr["type"]):
                        ftr["ID"] = ftr["Parent"]+"."+ftr["type"]

                    #link old to new ids for mRNA to use with CDS
                    if("RNA" in ftr["type"]):
                        mRNA_parent_dict[old_id]=ftr["ID"]

        return feature_list

    @staticmethod
    def _print_phytozome_gff(input_gff_file, feature_list):

        #Write modified feature ids to new file
        input_gff_file = input_gff_file.replace("gene", "edited_gene")+".gz"
        try:
            print "Printing to new file: "+input_gff_file
            gff_file_handle = gzip.open(input_gff_file, 'wb')
        except:
            print "Failed to open"

        for contig in sorted(feature_list.iterkeys()):
            for ftr in feature_list[contig]:

                #Re-build attributes
                attributes_dict = {}
                for attribute in ftr["attributes"]['raw'].split(";"):
                    attribute=attribute.strip()

                    #Sometimes empty string
                    if(attribute == ""):
                        continue

                    #Use of 1 to limit split as '=' character can also be made available later
                    #Sometimes lack of "=", assume spaces instead
                    if("=" in attribute):
                        key, value = attribute.split("=", 1)
                    elif(" " in attribute):
                        key, value = attribute.split(" ", 1)
                    else:
                        log("Warning: attribute "+attribute+" cannot be separated into key,value pair")

                    if(ftr[key] != value):
                        value = ftr[key]
                    attributes_dict[key]=value

                ftr["attributes"]=";".join(key+"="+attributes_dict[key] for key in attributes_dict.keys())

                new_line = "\t".join( str(ftr[key]) for key in ['contig', 'source', 'type', 'start', 'end',
                                                                'score', 'strand', 'phase', 'attributes'])
                gff_file_handle.write(new_line)
        gff_file_handle.close()
        return

    def _transform_feature(self, contig, in_feature):
        """Converts a feature from the gff ftr format into the appropriate
        format for a genome object """
        def _aliases(feat):
            keys = ('locus_tag', 'old_locus_tag', 'protein_id',
                    'transcript_id', 'gene', 'EC_number')
            alias_list = []
            for key in keys:
                if key in feat['attributes']:
                    alias_list.extend([(key, val) for val in feat['attributes'][key]])
            return alias_list

        if in_feature['start'] < 1 or in_feature['end'] > len(contig):
            self.warn("Feature with invalid location for specified "
                      "contig: " + str(in_feature))
            if self.strict:
                raise ValueError("Features must match fasta sequence")
            return

        feat_seq = contig.seq[in_feature['start']-1:in_feature['end']]
        if in_feature['strand'] in {'-', '-1'}:
            feat_seq = feat_seq.reverse_complement()

        # if the feature ID is duplicated (CDS or transpliced gene) we only
        # need to update the location and dna_sequence
        if in_feature['ID'] in self.feature_dict:
            existing = self.feature_dict[in_feature['ID']]
            existing['location'].append(self._location(in_feature))
            existing['dna_sequence'] += str(feat_seq)
            existing['dna_sequence_length'] = len(existing['dna_sequence'])
            return

        # The following is common to all the feature types
        out_feat = {
            "id": in_feature['ID'],
            "type": in_feature['type'],
            "location": [self._location(in_feature)],
            "dna_sequence": str(feat_seq),
            "dna_sequence_length": len(feat_seq),
            "md5": hashlib.md5(str(feat_seq)).hexdigest(),
        }
        # add optional fields
        if 'note' in in_feature['attributes']:
            out_feat['note'] = in_feature['attributes']["note"][0]
        ont = self._get_ontology(in_feature)
        if ont:
            out_feat['ontology_terms'] = ont
        aliases = _aliases(in_feature)
        if aliases:
            out_feat['aliases'] = aliases
        if 'db_xref' in in_feature['attributes']:
            out_feat['db_xrefs'] = [tuple(x.split(":")) for x in
                                   in_feature['attributes']['db_xref']]
        if 'product' in in_feature['attributes']:
            out_feat['functions'] = in_feature['attributes']["product"]
        parent_id = in_feature.get('Parent', '')
        if parent_id and parent_id not in self.feature_dict:
            raise ValueError("Parent ID: {} was not found in feature ID list.")

        # if the feature is a exon or UTR, it will only be used to update the
        # location and sequence of it's parent, we add the info to it parent
        # feature but not the feature dict
        if in_feature['type'] in ('exon', 'five_prime_UTR', 'three_prime_UTR',
                                  'start_codon', 'stop_codon'):
            if parent_id:
                # TODO: add location checks and warnings
                parent = self.feature_dict[parent_id]
                if in_feature['type'] not in parent:
                    parent[in_feature['type']] = []
                parent[in_feature['type']].append(out_feat)
            return

        # add type specific features
        elif in_feature['type'] == 'gene':
            out_feat['protein_translation_length'] = 0
            out_feat['cdss'] = []

        elif in_feature['type'] == 'CDS':
            if parent_id:
                parent = self.feature_dict[parent_id]
                if 'cdss' in parent:  # parent must be a gene
                    parent['cdss'].append(in_feature['ID'])
                    out_feat['parent_gene'] = parent_id
                else:  # parent must be mRNA
                    parent['cds'] = in_feature['ID']
                    out_feat['parent_mrna'] = parent_id
                    parent_gene = self.feature_dict[parent['parent_gene']]
                    parent_gene['cdss'].append(in_feature['ID'])
                    out_feat['parent_gene'] = parent['parent_gene']
            # keep track of CDSs for post processing
            self.cdss.add(out_feat['id'])

        elif in_feature['type'] == 'mRNA':
            if parent_id:
                parent = self.feature_dict[parent_id]
                if 'mrnas' not in parent:
                    parent['mrnas'] = []
                if 'cdss' in parent:  # parent must be a gene
                    parent['mrnas'].append(in_feature['ID'])
                    out_feat['parent_gene'] = parent_id

        else:
            out_feat["type"] = in_feature['type']
            if parent_id:
                # TODO: add location checks and warnings
                parent = self.feature_dict[parent_id]
                if 'children' not in parent:
                    parent['children'] = []
                parent['children'].append(out_feat['id'])
                out_feat['parent_gene'] = parent_id

        self.feature_dict[out_feat['id']] = out_feat

    def _process_cdss(self):
        """Because CDSs can have multiple fragments, it's necessary to go
        back over them to calculate a final protein sequence"""
        for cds_id in self.cdss:
            cds = self.feature_dict[cds_id]
            try:
                prot_seq = str(Seq(cds['dna_sequence']).translate(
                            self.code_table, cds=True).strip("*"))
            except TranslationError as e:
                cds['warnings'] = cds.get('warnings', []) + [str(e)]
                prot_seq = ""

            cds.update({
                "protein_translation": prot_seq,
                "protein_md5": hashlib.md5(prot_seq).hexdigest(),
                "protein_translation_length": len(prot_seq),
            })
            if 'parent_gene' in cds:
                parent_gene = self.feature_dict[cds['parent_gene']]
                propagate_cds_props_to_gene(cds, parent_gene)
            elif self.generate_genes:
                spoof = copy.copy(cds)
                spoof['type'] = 'gene'
                spoof['id'] = cds['id']+"_gene"
                spoof['cdss'] = [cds['id']]
                self.feature_dict[spoof['id']] = spoof
                cds['parent_gene'] = spoof['id']
            else:
                raise ValueError(warnings['no_spoof'])

            self.feature_dict[cds['id']] = cds

    def _update_from_exons(self, feature):
        """This function updates the sequence and location of a feature based
            on it's UTRs, CDSs and exon information"""
        # note that start and end here are in direction of translation
        def start(loc):
            return loc[0][1]

        def end(loc):
            if loc[-1][2] == "+":
                return loc[-1][1] + loc[-1][3] + 1
            else:
                return loc[-1][1] - loc[-1][3] - 1

        if 'exon' in feature:
            # update the feature with the exon locations and sequences
            feature['location'] = [x['location'][0] for x in feature['exon']]
            feature['dna_sequence'] = "".join(
                x['dna_sequence'] for x in feature['exon'])
            feature['dna_sequence_length'] = len(feature['dna_sequence'])

        # construct feature location from utrs and cdss if present
        elif 'cds' in feature:
            cds = [copy.copy(self.feature_dict[feature['cds']])]
            locs = []
            seq = ""
            for frag in feature.get('five_prime_UTR', []) + cds + \
                    feature.get('three_prime_UTR', []):

                # merge into last location if adjacent
                if locs and abs(end(locs) - start(frag['location'])) == 1:
                    # extend the location length by the length of the first
                    # location in the fragment
                    first = frag['location'].pop(0)
                    locs[-1][3] += first[3]

                locs.extend(frag['location'])
                seq += frag['dna_sequence']

            feature['location'] = locs
            feature['dna_sequence'] = seq
            feature['dna_sequence_length'] = len(seq)

        # remove these properties as they are no longer needed
        for x in ['five_prime_UTR', 'three_prime_UTR', 'exon']:
            feature.pop(x, None)

        else:
            ValueError('Feature {} must contain either exon or cds data to '
                       'construct an accurate location and sequence'.format(
                        feature['id']))

    def _gen_genome_info(self, core_genome_name, scientific_name, assembly_ref,
                         source, assembly, input_gff_file, molecule_type):
        """
        _gen_genome_info: generate genome info

        """
        genome = dict()
        genome["id"] = core_genome_name
        genome["scientific_name"] = scientific_name
        genome["assembly_ref"] = assembly_ref
        genome['molecule_type'] = molecule_type
        genome["features"] = []
        genome["cdss"] = []
        genome["mrnas"] = []
        genome['non_coding_features'] = []
        genome["gc_content"] = assembly["gc_content"]
        genome["dna_size"] = assembly["dna_size"]
        genome['md5'] = assembly['md5']
        genome['contig_ids'], genome['contig_lengths'] = zip(
            *[(k, v['length']) for k, v in assembly['contigs'].items()])
        genome['num_contigs'] = len(assembly['contigs'])
        genome["ontology_events"] = [{
            "method": "GenomeFileUtils Genbank uploader from annotations",
            "method_version": self.version,
            "timestamp": self.time_string,
            # TODO: remove this hardcoding
            "id": "GO",
            "ontology_ref": "KBaseOntology/gene_ontology"
        }]
        genome['ontologies_present'] = dict(self.ontologies_present)
        genome['taxonomy'], genome['taxon_ref'], genome['domain'], \
            genome["genetic_code"] = self.gi.retrieve_taxon(self.taxon_wsname,
                                                            genome['scientific_name'])
        genome['source'], genome['genome_tiers'] = self.gi.determine_tier(
            source)

        # Phytozome gff files are not compatible with the RNASeq Pipeline
        # so it's better to build from the object than cache the file
        if self.is_phytozome:
            gff_file_to_shock = self.dfu.file_to_shock(
                {'file_path': input_gff_file, 'make_handle': 1, 'pack': "gzip"})
            genome['gff_handle_ref'] = gff_file_to_shock['handle']['hid']

        # sort features into their respective arrays
        for feature in self.feature_dict.values():
            self.feature_counts[feature['type']] += 1
            if feature['type'] == 'CDS':
                del feature['type']
                genome['cdss'].append(feature)
            elif feature['type'] == 'mRNA':
                self._update_from_exons(feature)
                del feature['type']
                genome['mrnas'].append(feature)
            elif feature['type'] == 'gene':
                if genome['cdss']:
                    del feature['type']
                    self.feature_counts["protein_encoding_gene"] += 1
                    genome['features'].append(feature)
                else:
                    feature.pop('mrnas', None)
                    feature.pop('cdss', None)
                    self.feature_counts["non-protein_encoding_gene"] += 1
                    genome['non_coding_features'].append(feature)
            else:
                if 'exon' in feature:
                    self._update_from_exons(feature)
                genome['non_coding_features'].append(feature)
        if self.warnings:
            genome['warnings'] = self.warnings
        genome['feature_counts'] = dict(self.feature_counts)

        return genome

    def _convert_ftr_object(self, old_ftr, contig):
        new_ftr = dict()
        new_ftr["id"] = old_ftr["ID"]

        dna_sequence = Seq(contig[old_ftr["start"]-1:old_ftr["end"]], IUPAC.ambiguous_dna)

        # reverse complement
        if(old_ftr["strand"] == "-"):
            dna_sequence = dna_sequence.reverse_complement()
            old_start = old_ftr["start"]
            old_ftr["start"] = old_ftr["end"]
            old_ftr["end"]=old_start

        new_ftr["dna_sequence"] = str(dna_sequence).upper()
        new_ftr["dna_sequence_length"] = len(dna_sequence)
        new_ftr["md5"] = hashlib.md5(str(dna_sequence)).hexdigest()
        new_ftr["location"] = [[old_ftr["contig"], old_ftr["start"], 
                                old_ftr["strand"], len(dna_sequence)]]
        new_ftr["type"]=old_ftr["type"]

        new_ftr["aliases"]=list()
        for key in ("transcriptId", "proteinId", "PACid", "pacid"):
            if(key in old_ftr.keys()):
                new_ftr["aliases"].append(key+":"+old_ftr[key])

        return new_ftr

    def _utr_aggregation(self, utr_list, assembly, exons, exon_sequence):

        #create copies of locations and transcript
        utrs_exons = list(exons)
        utr_exon_sequence = exon_sequence

        five_prime_dna_sequence = ""
        three_prime_dna_sequence = ""
        five_prime_locations = list()
        three_prime_locations = list()

        for UTR in (utr_list):
            contig_sequence = assembly["contigs"][UTR["contig"]]["sequence"]
            UTR_ftr = self._convert_ftr_object(UTR, contig_sequence)  #reverse-complementation for negative strands done here

            #aggregate sequences and locations
            if("five_prime" in UTR_ftr["id"]):
                five_prime_dna_sequence += UTR_ftr["dna_sequence"]
                five_prime_locations.append(UTR_ftr["location"][0])
            if("three_prime" in UTR_ftr["id"]):
                three_prime_dna_sequence += UTR_ftr["dna_sequence"]
                three_prime_locations.append(UTR_ftr["location"][0])

        #Handle five_prime UTRs
        if(len(five_prime_locations)>0):

            #Sort UTRs by "start" (reverse-complement UTRs in Phytozome appear to be incorrectly ordered in the GFF file
            five_prime_locations = sorted(five_prime_locations, key=lambda x: x[1])

            #Merge last UTR with CDS if "next" to each other
            if(five_prime_locations[-1][1]+five_prime_locations[-1][3] == utrs_exons[0][1]):

                #Remove last UTR
                last_five_prime_location = five_prime_locations[-1]
                five_prime_locations = five_prime_locations[:-1]

                #"Add" last UTR to first exon
                utrs_exons[0][1]=last_five_prime_location[1]
                utrs_exons[0][3]+=last_five_prime_location[3]
                        
            #Prepend other UTRs if available
            if(len(five_prime_locations)>0):
                utrs_exons = five_prime_locations + utrs_exons

        utr_exon_sequence = five_prime_dna_sequence+utr_exon_sequence

        #Handle three_prime UTRs
        if(len(three_prime_locations)>0):

            #Sort UTRs by "start" (reverse-complement UTRs in Phytozome appear to be incorrectly ordered in the GFF file
            three_prime_locations = sorted(three_prime_locations, key=lambda x: x[1])

            #Merge first UTR with CDS if "next to each other
            if(utrs_exons[-1][1]+utrs_exons[-1][3] == three_prime_locations[0][1]):

                #Remove first UTR
                first_three_prime_location = three_prime_locations[0]
                three_prime_locations = three_prime_locations[1:]

                #"Add" first UTR to last exon
                utrs_exons[-1][3]+=first_three_prime_location[3]

        #Append other UTRs if available
        if(len(three_prime_locations)>0):
            utrs_exons = utrs_exons + three_prime_locations

        utr_exon_sequence += three_prime_dna_sequence

        return (utrs_exons, utr_exon_sequence)

    def _cds_aggregation_translation(self, cds_list, feature_list, assembly, issues):

        dna_sequence = ""
        locations = list()

        # collect phases, and lengths of exons
        # right now, this is only for the purpose of error reporting
        phases = list()
        exons = list()

        #Saving parent mRNA identifier
        Parent_mRNA = cds_list[0]["id"]
        for CDS in (cds_list):
            ftr = feature_list[CDS["index"]]
            phases.append(ftr["phase"])
            Parent_mRNA=ftr["Parent"]

            contig_sequence = assembly["contigs"][ftr["contig"]]["sequence"]
            CDS_ftr = self._convert_ftr_object(ftr, contig_sequence) #reverse-complementation for negative strands done here
            exons.append(len(CDS_ftr["dna_sequence"]))

            # Remove base(s) according to phase, but only for first CDS
            if(CDS == cds_list[0] and int(ftr["phase"]) != 0):
                log("Adjusting phase for first CDS: "+CDS["id"])
                CDS_ftr["dna_sequence"] = CDS_ftr["dna_sequence"][int(ftr["phase"]):]

            #aggregate sequences and locations
            dna_sequence += CDS_ftr["dna_sequence"]
            locations.append(CDS_ftr["location"][0])

        # translate sequence
        dna_sequence_obj = Seq(dna_sequence, IUPAC.ambiguous_dna)
        rna_sequence = dna_sequence_obj.transcribe()

        # incomplete gene model with no start codon
        if str(rna_sequence.upper())[:3] not in codon_table.start_codons:
            msg = "Missing start codon for {}. Possibly incomplete gene model.".format(Parent_mRNA)
            log(msg)

        # You should never have this problem, needs to be reported rather than "fixed"
        codon_count = len(str(rna_sequence)) % 3
        if codon_count != 0:
            msg = "Number of bases for RNA sequence for {} ".format(Parent_mRNA)
            msg += "is not divisible by 3. "
            msg += "The resulting protein may well be mis-translated."
            log(msg)
            issues.append(Parent_mRNA)

        protein_sequence = Seq("")
        try:
            protein_sequence = rna_sequence.translate()
        except CodonTable.TranslationError as te:
            log("TranslationError for: "+feature_object["id"], phases, exons, " : "+str(te))

        return (locations,dna_sequence.upper(),str(protein_sequence).upper())
