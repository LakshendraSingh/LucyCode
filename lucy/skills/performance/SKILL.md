---
name: performance
description: Performance optimization and profiling expertise
version: "1.0.0"
activates_on:
  keywords: ["performance", "slow", "optimize", "speed", "profile", "benchmark", "latency", "throughput", "memory"]
tags: ["performance", "optimization"]
priority: 8
---

# Performance Optimization

## Methodology
1. **Measure first**: Never optimize without profiling data
2. **Find the bottleneck**: Focus on the 20% causing 80% of slowness
3. **Optimize algorithmically first**: O(n²) → O(n log n) beats micro-optimization
4. **Verify improvement**: Benchmark before and after

## Common Optimizations
- **Algorithm**: Use appropriate data structures (hashmap vs list, etc.)
- **I/O**: Batch operations, use async, buffer reads/writes
- **Memory**: Reduce allocations, use generators/streams, pool objects
- **Caching**: Memoize expensive computations, use LRU cache
- **Concurrency**: Parallelize independent work, use connection pools
- **Database**: Index queries, avoid N+1, denormalize reads

## Anti-Patterns to Flag
- Premature optimization (optimize what matters)
- Unnecessary copies of large data
- Synchronous I/O in async context
- Unbounded caches
- String concatenation in loops
