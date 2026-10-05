# -*- coding: utf-8 -*-
import numpy as np
import highspy
from scipy import sparse
from scipy.optimize import linprog
from types import SimpleNamespace

FOM = 0.025
def crf(life, r=0.07):
    return r * (1 + r) ** life / ((1 + r) ** life - 1)
CRF_LI, CRF_LDES = crf(15), crf(20)
P_LI, P_LDES = 280.0, 1000.0          # USD/kW
RTE_LI, RTE_LDES = 0.86, 0.60
ETAc_LI, ETAd_LI = RTE_LI ** 0.5, RTE_LI ** 0.5
ETAc_LD, ETAd_LD = RTE_LDES ** 0.5, RTE_LDES ** 0.5


def solve_dispatch(d_eff, fit, gen1, anc1, ecost_li, ecost_ldes,
                   voll=10000.0, ob_max=5.0, rel_target=1.0, cyclic=True,
                   batch_arrival_mw=0.0, deadline_h=0, batch_capacity_multiple=2.0,
                   lp_method='highs', warm_basis=None, return_basis=False):
    d_eff = np.asarray(d_eff, float); fit = np.asarray(fit, float)
    if not 0.0 <= rel_target <= 1.0:
        raise ValueError('rel_target must lie in [0,1]')
    if batch_arrival_mw < 0 or int(deadline_h) != deadline_h or deadline_h < 0:
        raise ValueError('Batch arrival and integer deadline must be nonnegative')
    if batch_arrival_mw > 0 and np.min(d_eff - batch_arrival_mw) < -1e-8:
        raise ValueError('The fixed demand component cannot be negative')
    T = d_eff.size
    base = 5
    flex = batch_arrival_mw > 0
    N = base + (10 if flex else 8) * T
    # column offsets
    cCHGli, cDISli, cSOCli = base + 0*T, base + 1*T, base + 2*T
    cCHGld, cDISld, cSOCld = base + 3*T, base + 4*T, base + 5*T
    cCUR, cUNS = base + 6*T, base + 7*T
    cBATCH, cBACKLOG = base + 8*T, base + 9*T

    # objective
    c = np.zeros(N)
    c[0] = gen1 + anc1
    c[1] = (CRF_LI + FOM) * P_LI * 1000.0
    c[2] = (CRF_LI + FOM) * ecost_li * 1000.0
    c[3] = (CRF_LDES + FOM) * P_LDES * 1000.0
    c[4] = (CRF_LDES + FOM) * ecost_ldes * 1000.0
    c[cUNS:cUNS + T] = voll

    rows, cols, vals = [], [], []
    def add(r, cc, v):
        rows.append(r); cols.append(cc); vals.append(v)

    # --- A_eq: balance (T) + SOC_Li (T) + SOC_LDES (T) ---
    neqs = (4 if flex else 3) * T
    beq = np.zeros(neqs)
    # balance rows 0..T-1
    t = np.arange(T)
    add_r = 0
    for i in range(T):
        add(i, 0, fit[i])                 # fit*ob
        add(i, cDISli + i, 1.0); add(i, cDISld + i, 1.0)
        add(i, cCHGli + i, -1.0); add(i, cCHGld + i, -1.0)
        add(i, cCUR + i, -1.0); add(i, cUNS + i, 1.0)
        if flex:
            add(i, cBATCH + i, -1.0)
    beq[:T] = d_eff - batch_arrival_mw if flex else d_eff
    # SOC recursion (cyclic) for each tech
    for (r0, cCHG, cDIS, cSOC, etac, etad) in [
        (T,    cCHGli, cDISli, cSOCli, ETAc_LI, ETAd_LI),
        (2*T,  cCHGld, cDISld, cSOCld, ETAc_LD, ETAd_LD)]:
        for i in range(T):
            add(r0 + i, cSOC + i, 1.0)
            if cyclic or i > 0:
                add(r0 + i, cSOC + ((i - 1) % T), -1.0)
            add(r0 + i, cCHG + i, -etac)
            add(r0 + i, cDIS + i, 1.0 / etad)
    if flex:
        for i in range(T):
            add(3*T + i, cBACKLOG + i, 1.0)
            add(3*T + i, cBACKLOG + ((i-1) % T), -1.0)
            add(3*T + i, cBATCH + i, 1.0)
        beq[3*T:] = batch_arrival_mw
    A_eq = sparse.coo_matrix((vals, (rows, cols)), shape=(neqs, N)).tocsr()

    # --- A_ub: caps chg<=P, dis<=P, soc<=E for each tech (6T rows) ---
    ru, cu, vu = [], [], []
    def addu(r, cc, v):
        ru.append(r); cu.append(cc); vu.append(v)
    r = 0
    for (cCHG, cDIS, cSOC, colP, colE) in [
        (cCHGli, cDISli, cSOCli, 1, 2),
        (cCHGld, cDISld, cSOCld, 3, 4)]:
        for i in range(T):
            addu(r, cCHG + i, 1.0); addu(r, colP, -1.0); r += 1
        for i in range(T):
            addu(r, cDIS + i, 1.0); addu(r, colP, -1.0); r += 1
        for i in range(T):
            addu(r, cSOC + i, 1.0); addu(r, colE, -1.0); r += 1
    nub = 6 * T
    if rel_target < 1.0:                              # reliability cap: sum(unserved) <= budget
        for i in range(T):
            addu(nub, cUNS + i, 1.0)
        nub += 1
    A_ub = sparse.coo_matrix((vu, (ru, cu)), shape=(nub, N)).tocsr()
    b_ub = np.zeros(nub)
    if rel_target < 1.0:
        b_ub[-1] = (1.0 - rel_target) * float(d_eff.sum())

    bounds = [(1.0, ob_max)] + [(0, None)] * (N - 1)
    if rel_target == 1.0:
        bounds[cUNS:cUNS + T] = [(0.0, 0.0)] * T
    if flex:
        bounds[cBATCH:cBATCH + T] = [(0.0, batch_capacity_multiple * batch_arrival_mw)] * T
        bounds[cBACKLOG:cBACKLOG + T] = [(0.0, deadline_h * batch_arrival_mw)] * T
    if lp_method == 'highspy':
        h = highspy.Highs()
        h.setOptionValue('output_flag', False)
        h.setOptionValue('threads', 1)
        h.setOptionValue('solver', 'simplex')
        matrix = sparse.vstack([A_eq,A_ub],format='csc')
        model = highspy.HighsLp()
        model.num_col_ = N
        model.num_row_ = matrix.shape[0]
        model.col_cost_ = c
        model.col_lower_ = np.array([b[0] for b in bounds],dtype=float)
        model.col_upper_ = np.array([highspy.kHighsInf if b[1] is None else b[1] for b in bounds],dtype=float)
        model.row_lower_ = np.r_[beq,np.full(len(b_ub),-highspy.kHighsInf)]
        model.row_upper_ = np.r_[beq,b_ub]
        model.a_matrix_.format_ = highspy.MatrixFormat.kColwise
        model.a_matrix_.start_ = matrix.indptr
        model.a_matrix_.index_ = matrix.indices
        model.a_matrix_.value_ = matrix.data
        h.passModel(model)
        if warm_basis is not None:
            h.setBasis(warm_basis)
        h.run()
        status = h.getModelStatus()
        optimal = status == highspy.HighsModelStatus.kOptimal
        res = SimpleNamespace(success=optimal,status=0 if optimal else int(status),
                              message=h.modelStatusToString(status),x=np.asarray(h.getSolution().col_value),
                              fun=h.getInfo().objective_function_value)
    else:
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=beq,
                      bounds=bounds, method=lp_method)
    if not res.success:
        return {'ok': False, 'msg': res.message, 'solver_status': int(res.status)}
    x = res.x
    ob = x[0]; P_li, E_li, P_ld, E_ld = x[1:5]
    unmet = x[cUNS:cUNS + T].sum()
    dis_li = x[cDISli:cDISli + T].sum(); dis_ld = x[cDISld:cDISld + T].sum()
    cur = x[cCUR:cCUR + T].sum()
    store_li = (CRF_LI + FOM) * (P_LI * P_li + ecost_li * E_li) * 1000.0
    store_ld = (CRF_LDES + FOM) * (P_LDES * P_ld + ecost_ldes * E_ld) * 1000.0
    E_D = float(d_eff.sum())
    eq_error = float(np.max(np.abs(A_eq @ x - beq)))
    ub_error = float(max(0.0, np.max(A_ub @ x - b_ub)))
    bound_error = max(max(0.0, float(b[0])-float(xi)) for b, xi in zip(bounds, x))
    bound_error = max(bound_error, max(max(0.0, float(xi)-float(b[1])) for b, xi in zip(bounds, x) if b[1] is not None))
    batch_energy_error = float(abs(x[cBATCH:cBATCH + T].sum() - batch_arrival_mw*T)) if flex else 0.0
    backlog_max = float(np.max(x[cBACKLOG:cBACKLOG + T])) if flex else 0.0
    result = {'ok': True, 'ob': ob, 'P_li': P_li, 'E_li': E_li, 'P_ld': P_ld, 'E_ld': E_ld,
            'solver_status': int(res.status), 'solver_message': res.message,
            'equality_max_abs_error_mw': eq_error, 'inequality_max_violation_mw': ub_error,
            'bound_max_violation': bound_error, 'objective_usd_yr': float(res.fun),
            'batch_energy_error_mwh': batch_energy_error, 'batch_backlog_max_mwh': backlog_max,
            'batch_arrival_mw': batch_arrival_mw, 'deadline_h': deadline_h,
            'solver_backend': lp_method,
            'store_usd_yr': store_li + store_ld, 'gen_usd_yr': gen1 * ob, 'anc_usd_yr': anc1 * ob,
            'unmet_mwh': unmet, 'curtail_mwh': cur, 'dis_li_mwh': dis_li, 'dis_ld_mwh': dis_ld,
            'ldes_energy_share': dis_ld / max(dis_li + dis_ld, 1e-9),
            'lcoe_store': (store_li + store_ld) / E_D, 'lcoe_gen': gen1 * ob / E_D,
            'lcoe_anc': anc1 * ob / E_D,
            'lcoe_elec': (gen1 * ob + anc1 * ob + store_li + store_ld) / E_D,
            'firm_share': 1.0 - unmet / E_D}
    if return_basis:
        result['_basis'] = h.getBasis()
        result['simplex_iterations'] = h.getInfo().simplex_iteration_count
        result['max_dual_infeasibility'] = h.getInfo().max_dual_infeasibility
    return result


