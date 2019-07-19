# -*- coding: utf-8 -*-

import os
import sys
import argparse
import logging
import subprocess
import numpy as np
import pandas as pd
import hdbscan
from Bio import SeqIO
from .binner import generate_bins
from .binner import scaffolds_to_bins
from collections.abc import Iterable
import warnings
warnings.filterwarnings(action='ignore', category=DeprecationWarning, module='sklearn')  # message="divide by zero encountered in divide")


_logger = logging.getLogger("BlendIt")


def hdbscan_clustering(input_embedding_file, output_dir, prefix, excluding_contig_file_or_list=None, min_cluster_size=10):

    # read in embedding file
    embedding_df =  pd.read_csv(input_embedding_file, sep='\t', header=0, index_col=0)

    # exclude contigs
    excluding_set = {}
    if isinstance(excluding_contig_file_or_list, Iterable):
        excluding_set = set(excluding_contig_file_or_list)
    elif isinstance(excluding_contig_file_or_list, str) and os.path.isfile(excluding_contig_file_or_list):
        try:
            contigs = pd.read_csv(excluding_contig_file_or_list, header=None)
            contigs.columns = ['Contig_ID']
            excluding_set = set(contigs.Contig_ID)
        except Exception as e:
            _logger.error("read excluding_contig_file_or_list failed: {0}".format(e))
    else:
        _logger.error("the excluding_contig_file_or_list has to be a file or a list!")

    if excluding_set:
        idx_rows = []
        for idx in embedding_df.index:
            if idx in excluding_set:
                idx_rows.append(idx)
        try:
            embedding_df.drop(idx_rows, axis=0, inplace=True)
        except Exception as e:
            _logger.error("excluding contigs failed: {e}".format(e=e))

    # hdbscan clustering
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size) #, allow_single_cluster=True)
    #clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, prediction_data=True)
    #soft_membership_vec = hdbscan.all_points_membership_vectors(clusterer=clusterer)
    cluster_labels = clusterer.fit_predict(embedding_df)
    cluster_df = pd.DataFrame(data=cluster_labels.transpose(),
                              columns=['cluster'],
                              index=embedding_df.index)
    # write output
    output_hdbscan_file = os.path.join(output_dir, prefix+"_hdbscan.tsv")
    cluster_df.to_csv(output_hdbscan_file, sep="\t", header=True, index=True)

    return output_hdbscan_file


def iterative_hdbscan_binning(embeddings, assembly, contig_length_file, output_dir, prefix, 
                              min_length_x=2000, min_length_y=10000, length_step=1000, min_cluster_size=10):

    scaffold2bin_files = []
    bin_folders = []
    for embedding_file in embeddings:
        dimred_method = embedding_file.split('.')[-1]
        _logger.info("clustering using hdbscan based on {0} embedding file ...".format(dimred_method))
        length_df = pd.read_csv(contig_length_file, sep="\t", index_col=0, header=0)
        for min_length in range(min_length_x, min_length_y+1, length_step):
            _logger.info("clustering using hdbscan with contigs >= {l} ...".format(l=min_length))
            drop_length_df = length_df[length_df.Length < min_length]
            drop_contig_list = drop_length_df.index
            hdbscan_cluster_file = hdbscan_clustering(embedding_file, output_dir, prefix+"_merged_{0}_min_{1}".format(dimred_method, min_length), 
                                                      excluding_contig_file_or_list=drop_contig_list, min_cluster_size=min_cluster_size)
            # generate bins
            _logger.info("generating bins for contigs >= {l} ...".format(l=min_length))
            generate_bins(hdbscan_cluster_file, assembly, output_dir, bin_folder=prefix+"_merged_{0}_min_{1}".format(dimred_method, min_length))
            # generate scaffold2bin files
            _logger.info("generating scaffold2bin file for contigs >= {0} ...".format(min_length))
            bin_folder = os.path.join(output_dir, prefix+"_merged_{0}_min_{1}".format(dimred_method, min_length))
            scaffold2bin = bin_folder + "_scaffold2bin.tsv"
            bin_folders.append(bin_folder)
            scaffold2bin_files.append(scaffold2bin)
            scaffolds_to_bins(bin_folder, scaffold2bin, suffix="fa")

    return scaffold2bin_files, bin_folders