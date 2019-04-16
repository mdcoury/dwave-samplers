# Copyright 2019 D-Wave Systems Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#
# =============================================================================
from __future__ import division

import collections
import inspect
import itertools
import unittest

import dimod
import numpy as np

from orang import OrangSampler


class TestConstruction(unittest.TestCase):
    def test_construction(self):
        sampler = OrangSampler()
        dimod.testing.assert_sampler_api(sampler)

        # check that the args exposed by parameters is consistent with the
        # sampler inputs
        # getargspec is deprecated in python3, but for backwards compatibility
        args = {arg for arg in inspect.getargspec(sampler.sample).args
                if arg != 'self' and arg != 'bqm'}
        self.assertEqual(set(sampler.parameters), args)

        self.assertEqual(sampler.properties, {'max_treewidth': 25})


class TestSample(unittest.TestCase):
    def test_empty(self):
        bqm = dimod.BinaryQuadraticModel.empty(dimod.SPIN)

        sampleset = OrangSampler().sample(bqm)
        dimod.testing.assert_response_energies(sampleset, bqm)

    def test_empty_num_reads(self):
        bqm = dimod.BinaryQuadraticModel.empty(dimod.SPIN)

        sampleset = OrangSampler().sample(bqm, num_reads=10)
        self.assertEqual(len(sampleset), 10)
        dimod.testing.assert_response_energies(sampleset, bqm)

    def test_consistent_dtype_empty(self):
        bqm_empty = dimod.BinaryQuadraticModel.empty(dimod.BINARY)
        bqm = dimod.BinaryQuadraticModel.from_qubo({(0, 0): -1, (0, 1): 1})

        sampleset_empty = OrangSampler().sample(bqm_empty)
        sampleset = OrangSampler().sample(bqm)

        self.assertEqual(sampleset_empty.record.sample.dtype,
                         sampleset.record.sample.dtype)
        self.assertEqual(sampleset_empty.record.energy.dtype,
                         sampleset.record.energy.dtype)

    def test_consistent_info(self):
        bqm_empty = dimod.BinaryQuadraticModel.empty(dimod.BINARY)
        bqm = dimod.BinaryQuadraticModel.from_qubo({(0, 0): -1, (0, 1): 1})

        sampleset_empty = OrangSampler().sample(bqm_empty)
        sampleset = OrangSampler().sample(bqm)

        self.assertEqual(set(sampleset.info), set(sampleset_empty.info))

    def test_consistent_info_with_marginals(self):
        bqm_empty = dimod.BinaryQuadraticModel.empty(dimod.BINARY)
        bqm = dimod.BinaryQuadraticModel.from_qubo({(0, 0): -1, (0, 1): 1})

        sampleset_empty = OrangSampler().sample(bqm_empty, marginals=True)
        sampleset = OrangSampler().sample(bqm, marginals=True)

        self.assertEqual(set(sampleset.info), set(sampleset_empty.info))

    def test_single_variable(self):
        bqm = dimod.BinaryQuadraticModel.from_ising({'a': -1}, {})

        samples = OrangSampler().sample(bqm, num_reads=1)

        self.assertEqual(len(samples), 1)
        dimod.testing.assert_response_energies(samples, bqm)

    def test_single_interaction(self):
        bqm = dimod.BinaryQuadraticModel.from_ising({'a': -1}, {'ab': 1})

        samples = OrangSampler().sample(bqm, num_reads=1)

        self.assertEqual(len(samples), 1)
        dimod.testing.assert_response_energies(samples, bqm)

    def test_larger_problem(self):
        bqm = dimod.BinaryQuadraticModel.from_ising({'a': -1}, {'ab': 1, 'bc': -1, 'cd': +1})

        samples = OrangSampler().sample(bqm, num_reads=1)

        self.assertEqual(len(samples), 1)
        dimod.testing.assert_response_energies(samples, bqm)


class TestMarginals:
    def test_spin_log_partition_function(self):
        bqm = self.bqm

        exact = dimod.ExactSolver().sample(bqm)

        # dev note: when migrating to python 3.4+ these should become subtests
        for beta in [.5, 1., 1.5, 2]:
            sampleset = OrangSampler().sample(bqm,
                                              marginals=True, num_reads=10,
                                              beta=beta)

            logZ = sampleset.info['log_partition_function']

            # use the exactsolver to get all of the samples/energies
            calculated_logZ = np.log(np.sum(np.exp(-beta*exact.record.energy)))

            self.assertAlmostEqual(logZ, calculated_logZ,
                                   msg='beta={}'.format(beta))

    def test_variable_marginals_analytic(self):
        bqm = self.bqm

        exact = dimod.ExactSolver().sample(bqm)

        # for each variable, we need the sum over all energies when variable
        # is low or high
        energies = {}
        for v in bqm:
            idx = exact.variables.index[v]

            hien = exact.record[exact.record.sample[:, idx] > 0].energy

            energies[v] = hien

        # dev note: when migrating to python 3.4+ these should become subtests
        for beta in [.5, 1., 1.5, 2]:
            sampleset = OrangSampler().sample(bqm,
                                              marginals=True, num_reads=1,
                                              beta=beta)

            logZ = sampleset.info['log_partition_function']
            variable_marginals = sampleset.info['variable_marginals']

            Z = np.exp(logZ)  # we're only doing small ones so this is ok

            for v, p in variable_marginals.items():
                hien = energies[v]  # energies associated with v > 0

                self.assertAlmostEqual(p, np.sum(np.exp(-beta*hien)) / Z)

    def test_variable_marginals_empirical(self):
        # check that the actual samples match the marginals
        bqm = self.bqm

        # dev note: when migrating to python 3.4+ these should become subtests
        for beta in [.5, 1., 1.5, 2]:
            # we only need one sample to get the marginals
            single_sample = OrangSampler().sample(bqm,
                                                  marginals=True, num_reads=1,
                                                  beta=beta)

            variable_marginals = single_sample.info['variable_marginals']

            n = 22500

            sampleset = OrangSampler().sample(bqm, marginals=True, num_reads=n,
                                              beta=beta)

            for v, p in variable_marginals.items():
                p_observed = np.sum(sampleset.samples()[:, v] > 0) / len(sampleset)

                self.assertAlmostEqual(p, p_observed, places=1)

    def test_interaction_marginals_analytic(self):
        bqm = self.bqm

        exact = dimod.ExactSolver().sample(bqm)

        for beta in [.5, 1., 1.5, 2]:
            sampleset = OrangSampler().sample(self.bqm, num_reads=1, beta=beta,
                                              marginals=True)

            logZ = sampleset.info['log_partition_function']
            interaction_marginals = sampleset.info['interaction_marginals']

            Z = np.exp(logZ)  # we're only doing small ones so this is ok

            total_p = 0  # for sanity check

            # calculate the marginals analytically from the energies
            analytic_marginals = {pair: collections.defaultdict(float)
                                  for pair in interaction_marginals}
            for sample, energy in exact.data(['sample', 'energy']):

                # probability for this sample
                p = np.sum(np.exp(-beta*energy)) / Z
                total_p += p

                for (u, v) in analytic_marginals:
                    config = (sample[u], sample[v])

                    analytic_marginals[(u, v)][config] += p

            self.assertAlmostEqual(total_p, 1)  # sanity check

            # check that analytic and orang's are the same
            for pair, combos in interaction_marginals.items():
                for config, p in combos.items():
                    self.assertAlmostEqual(p, analytic_marginals[pair][config])


class TestSingleVariableSPIN(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_ising({'a': -1}, {})


class TestSingleVariableSPIN2(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_ising({'a': 1}, {})


class TestSingleVariableBINARY(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_qubo({(0, 0): -1})


class TestSingleVariableBINARY(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_qubo({(0, 0): 1})


class TestSingleVariableWithOffsetSPIN(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_ising({'a': -1}, {}, .5)


class TestSingleVariableWithOffsetBINARY(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_qubo({(0, 0): -1}, offset=.5)


class TestSingleInteractionSPIN(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_ising({}, {'ab': -1})


class TestSingleInteractionSPIN2(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_ising({}, {'ab': 1})


class TestK3SPIN(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_ising({}, {'ab': .69, 'bc': 1, 'ac': .5})


class TestK3BINARY(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_qubo({'ab': .69, 'bc': 1, 'ac': .5})


class Test3pathBINARY(unittest.TestCase, TestMarginals):
    bqm = dimod.BinaryQuadraticModel.from_qubo({'ab': .69, 'bc': 1})
