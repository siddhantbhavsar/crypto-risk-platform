#!/usr/bin/env python3
"""Quick test to verify hop detection is working"""

import pandas as pd

from services.scoring.risk_engine import (
    build_tx_graph,
    k_hop_layers_undirected,
    neighbors_undirected,
)

# Load data
txs = pd.read_csv("data/transactions.csv")
print(f"Loaded {len(txs)} transactions")

# Build graph
g = build_tx_graph(txs)
print(f"Graph has {g.number_of_nodes()} nodes and {g.number_of_edges()} edges")

# Test for Vitalik's wallet
wallet = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"

if wallet not in g:
    print(f"❌ Wallet {wallet} not found in graph!")
else:
    print(f"✅ Wallet {wallet} found in graph")
    print(f"   In-degree: {g.in_degree(wallet)}, Out-degree: {g.out_degree(wallet)}")
    
    # Test neighbors_undirected
    hop1_neighbors = neighbors_undirected(g, wallet)
    print(f"\n🔍 Direct neighbors (hop 1): {len(hop1_neighbors)}")
    
    if hop1_neighbors:
        # Pick one hop-1 neighbor and check its neighbors
        sample_hop1 = list(hop1_neighbors)[0]
        hop2_from_sample = neighbors_undirected(g, sample_hop1)
        print(f"   Neighbors of {sample_hop1[:10]}... (a hop-1 node): {len(hop2_from_sample)}")
        
        # How many of those are NOT visited (wallet or hop1)?
        visited = {wallet} | hop1_neighbors
        hop2_new = hop2_from_sample - visited
        print(f"   New nodes from this hop-1 neighbor (potential hop-2): {len(hop2_new)}")
        if hop2_new:
            print(f"   Sample hop-2 nodes: {list(hop2_new)[:3]}")
    
    # Test k-hop layers
    for hops in [1, 2, 3]:
        layers = k_hop_layers_undirected(g, wallet, hops)
        print(f"\n📊 {hops}-hop exploration:")
        for h, layer in enumerate(layers):
            print(f"   Hop {h}: {len(layer)} nodes")
        
        if hops == 2 and len(layers) > 2:
            # Show some examples from hop 2
            hop2_nodes = list(layers[2])[:5]
            print(f"   Example hop-2 nodes: {hop2_nodes}")
            
            # Verify they're 2 hops away
            if hop2_nodes:
                test_node = hop2_nodes[0]
                print(f"   Verifying {test_node[:10]}... is 2 hops away:")
                print(f"     - Is in graph: {test_node in g}")
                print(f"     - Direct neighbor of wallet: {test_node in neighbors_undirected(g, wallet)}")

