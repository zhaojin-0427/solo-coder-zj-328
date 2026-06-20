from typing import Optional, Dict, Any
from .base import BaseRepository
from ..db_utils import json_dumps, json_loads, bool_to_int, int_to_bool, now_iso, enum_value
from ..schemas import (
    StatsItemMissRate, StatsTopErrorMaterial, StatsAgentDistribution, StatsOverall
)

EXCEPTION_TYPE_NAMES = {
    "window_reject": "窗口退回",
    "material_invalid": "材料被判无效",
    "elder_absent": "老人未到场",
    "companion_late": "陪同人迟到",
    "supplement_fail": "现场补件失败",
    "policy_changed": "窗口政策变更",
    "elder_unwell": "老人身体不适",
    "other": "其他异常"
}


class StatsRepository(BaseRepository):

    def get_overall_stats(self, item_code: Optional[str] = None, limit_items: int = 10, limit_materials: int = 10) -> StatsOverall:
        with self._connect() as conn:
            c = conn.cursor()

            base_sql = "SELECT COUNT(*) as total, SUM(CASE WHEN is_pass = 0 THEN 1 ELSE 0 END) as miss_cnt, AVG(make_up_count) as avg_makeup FROM verification_history"
            params = []
            if item_code:
                base_sql += " WHERE item_code = ?"
                params.append(item_code)
            c.execute(base_sql, params)
            row = c.fetchone()
            total = row["total"] or 0
            miss_cnt = row["miss_cnt"] or 0
            avg_makeup = row["avg_makeup"] or 0.0
            overall_miss_rate = round(miss_cnt / total, 4) if total > 0 else 0.0

            item_sql = """
                SELECT si.item_code, si.item_name,
                       COUNT(vh.id) as total_queries,
                       SUM(CASE WHEN vh.is_pass = 1 THEN 1 ELSE 0 END) as pass_cnt,
                       SUM(CASE WHEN vh.is_pass = 0 THEN 1 ELSE 0 END) as miss_cnt
                FROM service_items si
                LEFT JOIN verification_history vh ON si.item_code = vh.item_code
            """
            iparams = []
            if item_code:
                item_sql += " WHERE si.item_code = ?"
                iparams.append(item_code)
            item_sql += " GROUP BY si.item_code ORDER BY miss_cnt DESC, total_queries DESC LIMIT ?"
            iparams.append(limit_items)
            c.execute(item_sql, iparams)
            top_items = []
            for r in c.fetchall():
                tq = r["total_queries"] or 0
                mc = r["miss_cnt"] or 0
                pc = r["pass_cnt"] or 0
                top_items.append(StatsItemMissRate(
                    item_code=r["item_code"],
                    item_name=r["item_name"],
                    total_queries=tq,
                    pass_count=pc,
                    miss_count=mc,
                    miss_rate=round(mc / tq, 4) if tq > 0 else 0.0
                ))

            c.execute("""
                SELECT material_category, material_name,
                       COUNT(*) as miss_count
                FROM miss_material_details
                GROUP BY material_category, material_name
                ORDER BY miss_count DESC LIMIT ?
            """, (limit_materials,))
            top_materials = []
            rank = 0
            for r in c.fetchall():
                rank += 1
                mc = r["miss_count"] or 0
                rate = round(mc / miss_cnt, 4) if miss_cnt > 0 else 0.0
                top_materials.append(StatsTopErrorMaterial(
                    category=r["material_category"],
                    name=r["material_name"],
                    miss_count=mc,
                    miss_rate=rate,
                    rank=rank
                ))

            c.execute("""
                SELECT agent_relation,
                       COUNT(*) as cnt,
                       AVG(missing_count) as avg_miss
                FROM verification_history
                WHERE is_agent = 1
                GROUP BY agent_relation
                ORDER BY cnt DESC
            """)
            agent_rows = c.fetchall()
            agent_total = sum(r["cnt"] for r in agent_rows) or 0
            agent_distribution = []
            for r in agent_rows:
                cnt = r["cnt"] or 0
                agent_distribution.append(StatsAgentDistribution(
                    agent_relation=r["agent_relation"] or "unknown",
                    count=cnt,
                    ratio=round(cnt / agent_total, 4) if agent_total > 0 else 0.0,
                    avg_miss_count=round(r["avg_miss"] or 0, 2)
                ))

            return StatsOverall(
                total_queries=total,
                overall_miss_rate=overall_miss_rate,
                avg_make_up_count=round(avg_makeup, 2),
                top_items=top_items,
                top_materials=top_materials,
                agent_distribution=agent_distribution
            )

    def get_pre_review_stats(self, item_code: Optional[str] = None, expected_window: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        now_iso_val = now_iso()
        base_sql = "SELECT COUNT(*) as total FROM pre_review_orders WHERE 1=1"
        params = []
        if item_code:
            base_sql += " AND item_code = ?"
            params.append(item_code)
        if expected_window:
            base_sql += " AND expected_window = ?"
            params.append(expected_window)
        if start_date:
            base_sql += " AND date(created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            base_sql += " AND date(created_at) <= date(?)"
            params.append(end_date)
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(base_sql, params)
            total_orders = c.fetchone()["total"] or 0

            pass_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as pass_cnt") + " AND is_pass = 1"
            c.execute(pass_sql, params)
            pass_count = c.fetchone()["pass_cnt"] or 0

            dup_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as dup_cnt") + " AND is_duplicate = 1"
            c.execute(dup_sql, params)
            duplicate_count = c.fetchone()["dup_cnt"] or 0

            avg_sql = base_sql.replace("COUNT(*) as total", "AVG(total_missing) as avg_miss")
            c.execute(avg_sql, params)
            avg_missing = round(c.fetchone()["avg_miss"] or 0.0, 2)

            exp_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as exp_cnt") + " AND is_pass = 0 AND suggestion_deadline < ?"
            exp_params = params + [now_iso_val]
            c.execute(exp_sql, exp_params)
            expired_count = c.fetchone()["exp_cnt"] or 0

            supp_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as supp_cnt") + " AND status IN ('supplementing','pending') AND supplement_count > 0"
            c.execute(supp_sql, params)
            supplement_in_progress_count = c.fetchone()["supp_cnt"] or 0

            item_miss_sql = """
                SELECT si.item_code, si.item_name,
                       COUNT(pr.id) as order_count,
                       AVG(pr.total_missing) as avg_miss
                FROM service_items si
                LEFT JOIN pre_review_orders pr ON si.item_code = pr.item_code
                WHERE 1=1
            """
            iparams = []
            if expected_window:
                item_miss_sql += " AND pr.expected_window = ?"
                iparams.append(expected_window)
            if start_date:
                item_miss_sql += " AND date(pr.created_at) >= date(?)"
                iparams.append(start_date)
            if end_date:
                item_miss_sql += " AND date(pr.created_at) <= date(?)"
                iparams.append(end_date)
            item_miss_sql += " GROUP BY si.item_code ORDER BY order_count DESC, avg_miss DESC LIMIT 20"
            c.execute(item_miss_sql, iparams)
            item_avg_missing = []
            for r in c.fetchall():
                item_avg_missing.append({
                    "item_code": r["item_code"],
                    "item_name": r["item_name"],
                    "order_count": r["order_count"] or 0,
                    "avg_missing_count": round(r["avg_miss"] or 0.0, 2)
                })

            mat_combo_sql = """
                SELECT pr.missing_list_json, COUNT(*) as cnt
                FROM pre_review_orders pr
                WHERE pr.is_pass = 0 AND pr.missing_list_json != '[]'
            """
            mparams = []
            if item_code:
                mat_combo_sql += " AND pr.item_code = ?"
                mparams.append(item_code)
            if expected_window:
                mat_combo_sql += " AND pr.expected_window = ?"
                mparams.append(expected_window)
            if start_date:
                mat_combo_sql += " AND date(pr.created_at) >= date(?)"
                mparams.append(start_date)
            if end_date:
                mat_combo_sql += " AND date(pr.created_at) <= date(?)"
                mparams.append(end_date)
            mat_combo_sql += " GROUP BY pr.missing_list_json ORDER BY cnt DESC LIMIT 10"
            c.execute(mat_combo_sql, mparams)
            top_combos = []
            rank = 0
            for r in c.fetchall():
                rank += 1
                try:
                    missing_list = json_loads(r["missing_list_json"])
                    mat_names = " + ".join([m.get("name", m.get("material_name", "?")) for m in missing_list[:5]])
                    if len(missing_list) > 5:
                        mat_names += f" 等{len(missing_list)}项"
                except Exception:
                    mat_names = "材料组合"
                top_combos.append({
                    "rank": rank,
                    "combo_count": r["cnt"],
                    "materials_preview": mat_names,
                    "materials_count": len(missing_list) if 'missing_list' in locals() else 0
                })

            window_pass_sql = """
                SELECT expected_window,
                       COUNT(*) as total,
                       SUM(CASE WHEN is_pass = 1 THEN 1 ELSE 0 END) as pass_cnt
                FROM pre_review_orders
                WHERE expected_window IS NOT NULL
            """
            wparams = []
            if item_code:
                window_pass_sql += " AND item_code = ?"
                wparams.append(item_code)
            if start_date:
                window_pass_sql += " AND date(created_at) >= date(?)"
                wparams.append(start_date)
            if end_date:
                window_pass_sql += " AND date(created_at) <= date(?)"
                wparams.append(end_date)
            window_pass_sql += " GROUP BY expected_window ORDER BY total DESC"
            c.execute(window_pass_sql, wparams)
            window_pass_rates = []
            for r in c.fetchall():
                total = r["total"] or 0
                pass_cnt = r["pass_cnt"] or 0
                window_pass_rates.append({
                    "window": r["expected_window"],
                    "total_orders": total,
                    "pass_count": pass_cnt,
                    "pass_rate": round(pass_cnt / total, 4) if total > 0 else 0.0
                })

        return {
            "total_orders": total_orders,
            "pass_count": pass_count,
            "pass_rate": round(pass_count / total_orders, 4) if total_orders > 0 else 0.0,
            "duplicate_count": duplicate_count,
            "duplicate_rate": round(duplicate_count / total_orders, 4) if total_orders > 0 else 0.0,
            "avg_missing_count": avg_missing,
            "expired_count": expired_count,
            "supplement_in_progress_count": supplement_in_progress_count,
            "item_avg_missing": item_avg_missing,
            "top_return_material_combos": top_combos,
            "window_pass_rates": window_pass_rates
        }

    def get_accompany_stats(self, community: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        base_sql = "SELECT * FROM accompany_appointments WHERE 1=1"
        params = []
        if community:
            base_sql += " AND community = ?"
            params.append(community)
        if start_date:
            base_sql += " AND date(created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            base_sql += " AND date(created_at) <= date(?)"
            params.append(end_date)
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as total"), params)
            total_appointments = c.fetchone()["total"] or 0
            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'completed'", params)
            completed_count = c.fetchone()["cnt"] or 0
            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'no_show'", params)
            no_show_count = c.fetchone()["cnt"] or 0
            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'cancelled'", params)
            cancelled_count = c.fetchone()["cnt"] or 0
            fu_sql = """
                SELECT AVG(fu.service_duration_minutes) as avg_dur,
                       SUM(CASE WHEN fu.is_elder_satisfied = 1 THEN 1 ELSE 0 END) as sat_cnt,
                       COUNT(fu.id) as fu_total
                FROM accompany_follow_ups fu
                JOIN accompany_appointments aa ON fu.appointment_id = aa.id
                WHERE 1=1
            """
            fu_params = []
            if community:
                fu_sql += " AND aa.community = ?"
                fu_params.append(community)
            if start_date:
                fu_sql += " AND date(aa.created_at) >= date(?)"
                fu_params.append(start_date)
            if end_date:
                fu_sql += " AND date(aa.created_at) <= date(?)"
                fu_params.append(end_date)
            c.execute(fu_sql, fu_params)
            fu_row = c.fetchone()
            avg_duration = round(fu_row["avg_dur"] or 0.0, 2)
            fu_total = fu_row["fu_total"] or 0
            sat_cnt = fu_row["sat_cnt"] or 0
            satisfaction_rate = round(sat_cnt / fu_total, 4) if fu_total > 0 else 0.0
            comm_sql = """
                SELECT aa.community,
                       COUNT(*) as total,
                       SUM(CASE WHEN aa.status = 'completed' THEN 1 ELSE 0 END) as completed_cnt,
                       SUM(CASE WHEN aa.status = 'no_show' THEN 1 ELSE 0 END) as no_show_cnt
                FROM accompany_appointments aa
                WHERE 1=1
            """
            comm_params = []
            if start_date:
                comm_sql += " AND date(aa.created_at) >= date(?)"
                comm_params.append(start_date)
            if end_date:
                comm_sql += " AND date(aa.created_at) <= date(?)"
                comm_params.append(end_date)
            comm_sql += " GROUP BY aa.community ORDER BY total DESC"
            c.execute(comm_sql, comm_params)
            community_stats = []
            for r in c.fetchall():
                total = r["total"] or 0
                cc = r["completed_cnt"] or 0
                ns = r["no_show_cnt"] or 0
                community_stats.append({
                    "community": r["community"],
                    "total_appointments": total,
                    "completed_count": cc,
                    "completion_rate": round(cc / total, 4) if total > 0 else 0.0,
                    "no_show_count": ns,
                    "no_show_rate": round(ns / total, 4) if total > 0 else 0.0
                })
            risk_sql = """
                SELECT aa.community,
                       COUNT(DISTINCT CASE WHEN aa.risk_level IN ('high', 'critical') THEN aa.elder_name || aa.contact_phone END) as high_risk_cnt,
                       SUM(CASE WHEN aa.risk_level IN ('high', 'critical') AND aa.status = 'completed' THEN 1 ELSE 0 END) as accompanied_cnt
                FROM accompany_appointments aa
                WHERE 1=1
            """
            risk_params = []
            if start_date:
                risk_sql += " AND date(aa.created_at) >= date(?)"
                risk_params.append(start_date)
            if end_date:
                risk_sql += " AND date(aa.created_at) <= date(?)"
                risk_params.append(end_date)
            risk_sql += " GROUP BY aa.community"
            c.execute(risk_sql, risk_params)
            risk_coverage_stats = []
            for r in c.fetchall():
                hr = r["high_risk_cnt"] or 0
                ac = r["accompanied_cnt"] or 0
                risk_coverage_stats.append({
                    "community": r["community"],
                    "high_risk_elder_count": hr,
                    "accompanied_count": ac,
                    "coverage_rate": round(ac / hr, 4) if hr > 0 else 0.0
                })
            workload_sql = """
                SELECT aa.recommended_companion_id as cid,
                       cr.name, cr.companion_type, cr.community,
                       COUNT(*) as total_services,
                       AVG(fu.service_duration_minutes) as avg_dur
                FROM accompany_appointments aa
                JOIN companion_resources cr ON aa.recommended_companion_id = cr.id
                LEFT JOIN accompany_follow_ups fu ON aa.id = fu.appointment_id
                WHERE aa.status = 'completed'
            """
            wl_params = []
            if community:
                workload_sql += " AND aa.community = ?"
                wl_params.append(community)
            if start_date:
                workload_sql += " AND date(aa.created_at) >= date(?)"
                wl_params.append(start_date)
            if end_date:
                workload_sql += " AND date(aa.created_at) <= date(?)"
                wl_params.append(end_date)
            workload_sql += " GROUP BY aa.recommended_companion_id ORDER BY total_services DESC LIMIT 20"
            c.execute(workload_sql, wl_params)
            companion_workload_ranking = []
            for r in c.fetchall():
                companion_workload_ranking.append({
                    "companion_id": r["cid"],
                    "companion_name": r["name"],
                    "companion_type": r["companion_type"],
                    "community": r["community"],
                    "total_services": r["total_services"] or 0,
                    "avg_duration_minutes": round(r["avg_dur"] or 0.0, 2)
                })
            mat_sql = """
                SELECT value as mat_name, COUNT(*) as fail_cnt
                FROM accompany_follow_ups,
                     json_each(accompany_follow_ups.failed_materials_json)
                WHERE accompany_follow_ups.materials_completed = 0
            """
            mat_params = []
            if start_date or end_date:
                mat_sql += " AND accompany_follow_ups.appointment_id IN (SELECT id FROM accompany_appointments WHERE 1=1"
                if start_date:
                    mat_sql += " AND date(created_at) >= date(?)"
                    mat_params.append(start_date)
                if end_date:
                    mat_sql += " AND date(created_at) <= date(?)"
                    mat_params.append(end_date)
                mat_sql += ")"
            mat_sql += " GROUP BY value ORDER BY fail_cnt DESC LIMIT 20"
            c.execute(mat_sql, mat_params)
            material_failure_ranking = []
            rank = 0
            for r in c.fetchall():
                rank += 1
                material_failure_ranking.append({
                    "material_name": r["mat_name"],
                    "failure_count": r["fail_cnt"] or 0,
                    "rank": rank
                })
        return {
            "total_appointments": total_appointments,
            "completed_count": completed_count,
            "completion_rate": round(completed_count / total_appointments, 4) if total_appointments > 0 else 0.0,
            "no_show_count": no_show_count,
            "no_show_rate": round(no_show_count / total_appointments, 4) if total_appointments > 0 else 0.0,
            "cancelled_count": cancelled_count,
            "avg_service_duration_minutes": avg_duration,
            "satisfaction_rate": satisfaction_rate,
            "community_stats": community_stats,
            "risk_coverage_stats": risk_coverage_stats,
            "companion_workload_ranking": companion_workload_ranking,
            "material_failure_ranking": material_failure_ranking
        }

    def get_exception_stats(self, item_code: Optional[str] = None, community: Optional[str] = None, expected_window: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        base_sql = "SELECT * FROM exception_disposal_orders WHERE 1=1"
        params = []
        if item_code:
            base_sql += " AND item_code = ?"
            params.append(item_code)
        if community:
            base_sql += " AND community = ?"
            params.append(community)
        if expected_window:
            base_sql += " AND expected_window = ?"
            params.append(expected_window)
        if start_date:
            base_sql += " AND date(created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            base_sql += " AND date(created_at) <= date(?)"
            params.append(end_date)

        with self._connect() as conn:
            c = conn.cursor()

            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as total"), params)
            total_exceptions = c.fetchone()["total"] or 0

            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'pending'", params)
            pending_count = c.fetchone()["cnt"] or 0

            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'in_progress'", params)
            in_progress_count = c.fetchone()["cnt"] or 0

            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'resolved'", params)
            resolved_count = c.fetchone()["cnt"] or 0

            c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'closed'", params)
            closed_count = c.fetchone()["cnt"] or 0

            now_iso_val = now_iso()
            timeout_sql = base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND latest_deadline < ? AND status NOT IN ('closed', 'resolved')"
            timeout_params = params + [now_iso_val]
            c.execute(timeout_sql, timeout_params)
            timeout_count = c.fetchone()["cnt"] or 0

            verify_sql = "SELECT COUNT(*) as cnt FROM verification_history"
            pr_sql = "SELECT COUNT(*) as cnt FROM pre_review_orders"
            acc_sql = "SELECT COUNT(*) as cnt FROM accompany_appointments"
            v_params = []
            p_params = []
            a_params = []
            if start_date:
                verify_sql += " WHERE date(created_at) >= date(?)"
                pr_sql += " WHERE date(created_at) >= date(?)"
                acc_sql += " WHERE date(created_at) >= date(?)"
                v_params.append(start_date)
                p_params.append(start_date)
                a_params.append(start_date)
                if end_date:
                    verify_sql += " AND date(created_at) <= date(?)"
                    pr_sql += " AND date(created_at) <= date(?)"
                    acc_sql += " AND date(created_at) <= date(?)"
                    v_params.append(end_date)
                    p_params.append(end_date)
                    a_params.append(end_date)
            elif end_date:
                verify_sql += " WHERE date(created_at) <= date(?)"
                pr_sql += " WHERE date(created_at) <= date(?)"
                acc_sql += " WHERE date(created_at) <= date(?)"
                v_params.append(end_date)
                p_params.append(end_date)
                a_params.append(end_date)

            c.execute(verify_sql, v_params)
            total_verify = c.fetchone()["cnt"] or 0
            c.execute(pr_sql, p_params)
            total_pr = c.fetchone()["cnt"] or 0
            c.execute(acc_sql, a_params)
            total_acc_for_rate = c.fetchone()["cnt"] or 0
            total_transactions = total_verify + total_pr + total_acc_for_rate
            raw_rate = (total_exceptions / total_transactions) if total_transactions > 0 else 0.0
            exception_rate = round(min(raw_rate, 1.0), 4)

            item_rank_sql = """
                SELECT si.item_code, si.item_name,
                       COUNT(eo.id) as exc_cnt
                FROM service_items si
                LEFT JOIN exception_disposal_orders eo ON si.item_code = eo.item_code
                WHERE 1=1
            """
            ir_params = []
            if community:
                item_rank_sql += " AND eo.community = ?"
                ir_params.append(community)
            if expected_window:
                item_rank_sql += " AND eo.expected_window = ?"
                ir_params.append(expected_window)
            if start_date:
                item_rank_sql += " AND date(eo.created_at) >= date(?)"
                ir_params.append(start_date)
            if end_date:
                item_rank_sql += " AND date(eo.created_at) <= date(?)"
                ir_params.append(end_date)
            item_rank_sql += " GROUP BY si.item_code ORDER BY exc_cnt DESC LIMIT 20"
            c.execute(item_rank_sql, ir_params)
            item_exception_ranking = []
            rank = 0
            for r in c.fetchall():
                rank += 1
                exc_cnt = r["exc_cnt"] or 0
                item_total_sql = "SELECT COUNT(*) as cnt FROM (" \
                                 "SELECT id FROM verification_history WHERE item_code = ? " \
                                 "UNION ALL SELECT id FROM pre_review_orders WHERE item_code = ? " \
                                 "UNION ALL SELECT id FROM accompany_appointments WHERE item_code = ?" \
                                 ") t"
                t_params = [r["item_code"], r["item_code"], r["item_code"]]
                if start_date or end_date:
                    item_total_sql = "SELECT COUNT(*) as cnt FROM (" \
                                     "SELECT id FROM verification_history WHERE item_code = ? {date_clause_v}" \
                                     " UNION ALL SELECT id FROM pre_review_orders WHERE item_code = ? {date_clause_pr}" \
                                     " UNION ALL SELECT id FROM accompany_appointments WHERE item_code = ? {date_clause_acc}" \
                                     ") t"
                    date_clause_v = ""
                    date_clause_pr = ""
                    date_clause_acc = ""
                    extra_params = []
                    if start_date:
                        date_clause_v += " AND date(created_at) >= date(?)"
                        date_clause_pr += " AND date(created_at) >= date(?)"
                        date_clause_acc += " AND date(created_at) >= date(?)"
                        extra_params.extend([start_date, start_date, start_date])
                    if end_date:
                        date_clause_v += " AND date(created_at) <= date(?)"
                        date_clause_pr += " AND date(created_at) <= date(?)"
                        date_clause_acc += " AND date(created_at) <= date(?)"
                        extra_params.extend([end_date, end_date, end_date])
                    item_total_sql = item_total_sql.format(
                        date_clause_v=date_clause_v,
                        date_clause_pr=date_clause_pr,
                        date_clause_acc=date_clause_acc
                    )
                    t_params.extend(extra_params)
                c.execute(item_total_sql, t_params)
                item_total = c.fetchone()["cnt"] or 0
                raw_item_rate = (exc_cnt / item_total) if item_total > 0 else 0.0
                item_exception_ranking.append({
                    "item_code": r["item_code"],
                    "item_name": r["item_name"],
                    "exception_count": exc_cnt,
                    "exception_rate": round(min(raw_item_rate, 1.0), 4),
                    "rank": rank
                })

            type_duration_sql = """
                SELECT exception_type,
                       COUNT(*) as cnt,
                       AVG((julianday(COALESCE(closed_at, ?)) - julianday(created_at)) * 1440) as avg_dur
                FROM exception_disposal_orders
                WHERE 1=1
            """
            td_params = [now_iso_val]
            if item_code:
                type_duration_sql += " AND item_code = ?"
                td_params.append(item_code)
            if community:
                type_duration_sql += " AND community = ?"
                td_params.append(community)
            if expected_window:
                type_duration_sql += " AND expected_window = ?"
                td_params.append(expected_window)
            if start_date:
                type_duration_sql += " AND date(created_at) >= date(?)"
                td_params.append(start_date)
            if end_date:
                type_duration_sql += " AND date(created_at) <= date(?)"
                td_params.append(end_date)
            type_duration_sql += " GROUP BY exception_type ORDER BY cnt DESC"
            c.execute(type_duration_sql, td_params)
            type_avg_duration = []
            for r in c.fetchall():
                type_avg_duration.append({
                    "exception_type": r["exception_type"],
                    "exception_type_name": EXCEPTION_TYPE_NAMES.get(r["exception_type"], r["exception_type"]),
                    "avg_duration_minutes": round(r["avg_dur"] or 0.0, 2),
                    "count": r["cnt"] or 0
                })

            failure_sql = """
                SELECT eo.exception_type, COUNT(*) as cnt
                FROM exception_disposal_orders eo
                WHERE eo.impact_completion = 1
            """
            f_params = []
            if item_code:
                failure_sql += " AND eo.item_code = ?"
                f_params.append(item_code)
            if community:
                failure_sql += " AND eo.community = ?"
                f_params.append(community)
            if expected_window:
                failure_sql += " AND eo.expected_window = ?"
                f_params.append(expected_window)
            if start_date:
                failure_sql += " AND date(eo.created_at) >= date(?)"
                f_params.append(start_date)
            if end_date:
                failure_sql += " AND date(eo.created_at) <= date(?)"
                f_params.append(end_date)
            failure_sql += " GROUP BY eo.exception_type ORDER BY cnt DESC LIMIT 10"
            c.execute(failure_sql, f_params)
            top_failure_reasons = []
            rank = 0
            for r in c.fetchall():
                rank += 1
                top_failure_reasons.append({
                    "reason": EXCEPTION_TYPE_NAMES.get(r["exception_type"], r["exception_type"]),
                    "count": r["cnt"] or 0,
                    "rank": rank
                })

            acc_exc_sql = base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND source_type = 'accompany_appointment'"
            c.execute(acc_exc_sql, params)
            accompany_exception_count = c.fetchone()["cnt"] or 0

            c.execute(acc_sql, a_params)
            accompany_total = c.fetchone()["cnt"] or 0
            raw_acc_rate = (accompany_exception_count / accompany_total) if accompany_total > 0 else 0.0
            accompany_exception_rate = round(min(raw_acc_rate, 1.0), 4)

            raw_timeout_rate = (timeout_count / total_exceptions) if total_exceptions > 0 else 0.0
            timeout_rate = round(min(raw_timeout_rate, 1.0), 4)

        return {
            "total_exceptions": total_exceptions,
            "exception_rate": exception_rate,
            "pending_count": pending_count,
            "in_progress_count": in_progress_count,
            "resolved_count": resolved_count,
            "closed_count": closed_count,
            "timeout_count": timeout_count,
            "timeout_rate": timeout_rate,
            "item_exception_ranking": item_exception_ranking,
            "type_avg_duration": type_avg_duration,
            "top_failure_reasons": top_failure_reasons,
            "accompany_exception_rate": accompany_exception_rate,
            "accompany_exception_count": accompany_exception_count,
            "accompany_total": accompany_total
        }

    def get_policy_stats(self, item_code: Optional[str] = None, community: Optional[str] = None, expected_window: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        with self._connect() as conn:
            c = conn.cursor()

            policy_sql = "SELECT COUNT(*) as cnt FROM policy_changes WHERE 1=1"
            policy_params = []

            active_sql = "SELECT COUNT(*) as cnt FROM policy_changes WHERE status = 'active'"
            active_params = []

            if start_date:
                policy_sql += " AND date(created_at) >= date(?)"
                active_sql += " AND date(created_at) >= date(?)"
                policy_params.append(start_date)
                active_params.append(start_date)
            if end_date:
                policy_sql += " AND date(created_at) <= date(?)"
                active_sql += " AND date(created_at) <= date(?)"
                policy_params.append(end_date)
                active_params.append(end_date)

            c.execute(policy_sql, policy_params)
            total_policy_changes = c.fetchone()["cnt"] or 0

            c.execute(active_sql, active_params)
            active_policy_count = c.fetchone()["cnt"] or 0

            warn_sql = "SELECT COUNT(*) as cnt FROM policy_warnings WHERE 1=1"
            warn_params = []
            confirmed_sql = "SELECT COUNT(*) as cnt FROM policy_warnings WHERE status = 'confirmed'"
            confirmed_params = []
            high_risk_sql = "SELECT COUNT(*) as cnt FROM policy_warnings WHERE status = 'unconfirmed' AND risk_level IN ('high', 'critical')"
            high_risk_params = []

            if item_code:
                warn_sql += " AND item_code = ?"
                confirmed_sql += " AND item_code = ?"
                high_risk_sql += " AND item_code = ?"
                warn_params.append(item_code)
                confirmed_params.append(item_code)
                high_risk_params.append(item_code)
            if community:
                warn_sql += " AND community = ?"
                confirmed_sql += " AND community = ?"
                high_risk_sql += " AND community = ?"
                warn_params.append(community)
                confirmed_params.append(community)
                high_risk_params.append(community)
            if expected_window:
                warn_sql += " AND expected_window = ?"
                confirmed_sql += " AND expected_window = ?"
                high_risk_sql += " AND expected_window = ?"
                warn_params.append(expected_window)
                confirmed_params.append(expected_window)
                high_risk_params.append(expected_window)
            if start_date:
                warn_sql += " AND date(created_at) >= date(?)"
                confirmed_sql += " AND date(created_at) >= date(?)"
                high_risk_sql += " AND date(created_at) >= date(?)"
                warn_params.append(start_date)
                confirmed_params.append(start_date)
                high_risk_params.append(start_date)
            if end_date:
                warn_sql += " AND date(created_at) <= date(?)"
                confirmed_sql += " AND date(created_at) <= date(?)"
                high_risk_sql += " AND date(created_at) <= date(?)"
                warn_params.append(end_date)
                confirmed_params.append(end_date)
                high_risk_params.append(end_date)

            c.execute(warn_sql, warn_params)
            total_warnings = c.fetchone()["cnt"] or 0

            c.execute(confirmed_sql, confirmed_params)
            confirmed_warnings = c.fetchone()["cnt"] or 0

            c.execute(high_risk_sql, high_risk_params)
            unconfirmed_high_risk = c.fetchone()["cnt"] or 0

            rank_sql = """
                SELECT pw.item_code, pw.item_name,
                       COUNT(*) as warning_count
                FROM policy_warnings pw
                WHERE 1=1
            """
            rank_params = []
            if item_code:
                rank_sql += " AND pw.item_code = ?"
                rank_params.append(item_code)
            if community:
                rank_sql += " AND pw.community = ?"
                rank_params.append(community)
            if expected_window:
                rank_sql += " AND pw.expected_window = ?"
                rank_params.append(expected_window)
            if start_date:
                rank_sql += " AND date(pw.created_at) >= date(?)"
                rank_params.append(start_date)
            if end_date:
                rank_sql += " AND date(pw.created_at) <= date(?)"
                rank_params.append(end_date)
            rank_sql += " GROUP BY pw.item_code ORDER BY warning_count DESC LIMIT 10"
            c.execute(rank_sql, rank_params)
            item_ranking = []
            rank = 0
            for r in c.fetchall():
                rank += 1
                item_ranking.append({
                    "rank": rank,
                    "item_code": r["item_code"] or "",
                    "item_name": r["item_name"] or "",
                    "warning_count": r["warning_count"] or 0
                })

            total_exc_sql = "SELECT COUNT(*) as cnt FROM exception_disposal_orders WHERE 1=1"
            total_exc_params = []
            policy_exc_sql = "SELECT COUNT(*) as cnt FROM exception_disposal_orders WHERE exception_type = 'policy_changed'"
            policy_exc_params = []

            if item_code:
                total_exc_sql += " AND item_code = ?"
                policy_exc_sql += " AND item_code = ?"
                total_exc_params.append(item_code)
                policy_exc_params.append(item_code)
            if start_date:
                total_exc_sql += " AND date(created_at) >= date(?)"
                policy_exc_sql += " AND date(created_at) >= date(?)"
                total_exc_params.append(start_date)
                policy_exc_params.append(start_date)
            if end_date:
                total_exc_sql += " AND date(created_at) <= date(?)"
                policy_exc_sql += " AND date(created_at) <= date(?)"
                total_exc_params.append(end_date)
                policy_exc_params.append(end_date)

            c.execute(total_exc_sql, total_exc_params)
            total_exceptions = c.fetchone()["cnt"] or 0

            c.execute(policy_exc_sql, policy_exc_params)
            policy_exception_count = c.fetchone()["cnt"] or 0

            policy_exception_ratio = round(policy_exception_count / total_exceptions, 4) if total_exceptions > 0 else 0.0

        return {
            "total_policy_changes": total_policy_changes,
            "active_policy_count": active_policy_count,
            "total_warnings": total_warnings,
            "confirmed_warnings": confirmed_warnings,
            "unconfirmed_high_risk_warnings": unconfirmed_high_risk,
            "item_policy_impact_ranking": item_ranking,
            "policy_exception_ratio": policy_exception_ratio,
            "policy_exception_count": policy_exception_count,
            "total_exceptions": total_exceptions
        }
