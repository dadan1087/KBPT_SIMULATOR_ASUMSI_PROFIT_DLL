import streamlit as st
from collections import deque
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import json
import base64
import random
import time

# ---------------------------- Data Model (Interaktif) ----------------------------
class Member:
    __slots__ = ('id','name','sponsor_id','parent_id','left_child_id','right_child_id','is_active',
                 'balance_cuan','balance_rich','total_spent','total_commission_received')
    def __init__(self, id, name, sponsor_id, parent_id=None, is_active=False):
        self.id = id
        self.name = name
        self.sponsor_id = sponsor_id
        self.parent_id = parent_id
        self.left_child_id = None
        self.right_child_id = None
        self.is_active = is_active
        self.balance_cuan = 0
        self.balance_rich = 0
        self.total_spent = 0
        self.total_commission_received = 0

# ---------------------------- Inisialisasi Session State (hanya sekali) ----------------------------
def init_interactive():
    """Inisialisasi state untuk mode interaktif (registrasi, belanja, visualisasi)."""
    if 'members' not in st.session_state:
        root = Member(1, "Perusahaan", sponsor_id=None, parent_id=None, is_active=True)
        st.session_state.members = {1: root}
        st.session_state.next_id = 2
        st.session_state.total_cash_in = 0
        st.session_state.total_bonus_cuan = 0
        st.session_state.total_bonus_rich = 0
        st.session_state.total_sponsor_bonus = 0
        st.session_state.transactions = []
        st.session_state.placement_queue = deque([1])
        st.session_state.selected_sponsor_id = 1
        st.session_state.reg_name = ""
        # Parameter komisi default
        st.session_state.cuan_percent = [0, 0.01, 0.01, 0.05, 0.03, 0.03, 0.02, 0.03, 0.07]
        st.session_state.rich_percent = [0, 0.05, 0.05, 0.04, 0.04, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01]
        st.session_state.cuan_max_level = 8
        st.session_state.rich_max_level = 10
        st.session_state.sponsor_bonus_percent = 0.20
        st.session_state.min_spend_active = 100000

# ---------------------------- Fungsi Placement (Interaktif) ----------------------------
def find_placement_cuan():
    members = st.session_state.members
    queue = deque([1])
    while queue:
        node_id = queue.popleft()
        node = members[node_id]
        if node.right_child_id is None:
            return node_id, False
        if node.left_child_id is None:
            return node_id, True
        queue.append(node.right_child_id)
        queue.append(node.left_child_id)
    return None, None

def register_member(sponsor_id, name):
    members = st.session_state.members
    if sponsor_id not in members:
        return None, f"Sponsor ID {sponsor_id} tidak ditemukan."
    if any(m.name.lower() == name.lower() for m in members.values()):
        return None, f"Nama '{name}' sudah terdaftar."
    new_id = st.session_state.next_id
    st.session_state.next_id += 1
    parent_id, is_left = find_placement_cuan()
    if parent_id is None:
        return None, "Tidak ada slot kosong."
    new_member = Member(new_id, name, sponsor_id, parent_id, is_active=True)
    members[new_id] = new_member
    parent = members[parent_id]
    if not is_left:
        parent.right_child_id = new_id
    else:
        parent.left_child_id = new_id
    st.session_state.placement_queue.append(new_id)
    side = "kanan" if not is_left else "kiri"
    info = (f"✅ Auto Cuan: anak {side} dari {parent.name} (ID:{parent.id})\n"
            f"✅ Auto Rich: sponsor langsung = {members[sponsor_id].name} (ID:{sponsor_id})")
    return new_member, info

# ---------------------------- Fungsi Komisi (Interaktif) ----------------------------
def get_ancestors_cuan(member_id, members, max_level):
    ancestors = []
    cur = members[member_id].parent_id
    level = 1
    while cur and level <= max_level:
        ancestors.append((cur, level))
        cur = members[cur].parent_id
        level += 1
    return ancestors

def get_ancestors_rich(member_id, members, max_level):
    ancestors = []
    cur = members[member_id].sponsor_id
    level = 1
    while cur and level <= max_level:
        ancestors.append((cur, level))
        cur = members[cur].sponsor_id
        level += 1
    return ancestors

def calculate_sponsor_bonus_chain(member_id, amount, members, percent):
    total_bonus = 0
    current = member_id
    while current:
        sponsor_id = members[current].sponsor_id
        if sponsor_id is None:
            break
        bonus = int(amount * percent)
        total_bonus += bonus
        members[sponsor_id].balance_cuan += bonus
        st.session_state.total_sponsor_bonus += bonus
        current = sponsor_id
        amount = bonus
    return total_bonus

def process_transaction_cuan(member_id, amount, apply_to_balance=False):
    members = st.session_state.members
    member = members[member_id]
    if amount >= st.session_state.min_spend_active:
        member.is_active = True
    if apply_to_balance:
        member.total_spent += amount
        st.session_state.total_cash_in += amount

    bonus_cuan = 0
    breakdown_cuan = []
    max_level = st.session_state.cuan_max_level
    ancestors = get_ancestors_cuan(member_id, members, max_level)
    for anc_id, lvl in ancestors:
        anc = members[anc_id]
        if anc.is_active:
            percent = st.session_state.cuan_percent[lvl] if lvl < len(st.session_state.cuan_percent) else 0
            komisi = int(amount * percent)
            if komisi > 0:
                if apply_to_balance:
                    anc.balance_cuan += komisi
                    anc.total_commission_received += komisi
                    st.session_state.total_bonus_cuan += komisi
                bonus_cuan += komisi
                breakdown_cuan.append((anc_id, anc.name, f"Matrix Level {lvl} ({percent*100:.0f}%)", komisi))

    sponsor_bonus_total = 0
    for anc_id, _, _, komisi in breakdown_cuan:
        if komisi > 0:
            sponsor_bonus_total += calculate_sponsor_bonus_chain(anc_id, komisi, members, st.session_state.sponsor_bonus_percent)

    return {
        'buyer_name': member.name, 'buyer_id': member_id, 'amount': amount,
        'member_active': member.is_active, 'ancestors_cuan': ancestors,
        'bonus_cuan': bonus_cuan, 'bonus_rich': 0,
        'total_bonus': bonus_cuan + sponsor_bonus_total,
        'breakdown_cuan': breakdown_cuan, 'breakdown_rich': []
    }

def process_transaction_rich(member_id, amount, apply_to_balance=False):
    members = st.session_state.members
    member = members[member_id]
    if apply_to_balance:
        member.total_spent += amount
        st.session_state.total_cash_in += amount

    bonus_rich = 0
    breakdown_rich = []
    max_level = st.session_state.rich_max_level
    ancestors_rich = get_ancestors_rich(member_id, members, max_level)
    for anc_id, lvl in ancestors_rich:
        percent = st.session_state.rich_percent[lvl] if lvl < len(st.session_state.rich_percent) else 0
        komisi = int(amount * percent)
        if komisi > 0:
            if apply_to_balance:
                members[anc_id].balance_rich += komisi
                st.session_state.total_bonus_rich += komisi
            bonus_rich += komisi
            breakdown_rich.append((anc_id, members[anc_id].name, f"Level {lvl} ({percent*100:.0f}%)", komisi))
    return {
        'buyer_name': member.name, 'buyer_id': member_id, 'amount': amount,
        'member_active': member.is_active, 'bonus_cuan': 0, 'bonus_rich': bonus_rich,
        'total_bonus': bonus_rich, 'breakdown_cuan': [], 'breakdown_rich': breakdown_rich
    }

# ---------------------------- Visualisasi (Interaktif) ----------------------------
def get_descendants_rich(root_id, members):
    result = []
    stack = [root_id]
    while stack:
        nid = stack.pop()
        if nid not in result:
            result.append(nid)
        for mid, m in members.items():
            if m.sponsor_id == nid:
                stack.append(mid)
    return result

def get_member_tree_cuan(root_id, members, search_id=None):
    if root_id not in members:
        return ""
    lines = ['digraph G {', '    rankdir=TB;', '    node [shape=box, style=filled, fillcolor=lightblue, fontname="Arial"];']
    lines.append('    margin=0;')
    queue = deque([root_id])
    while queue:
        nid = queue.popleft()
        node = members[nid]
        if search_id == nid:
            fillcolor = "yellow"
            fontcolor = "black"
        else:
            if node.is_active:
                fillcolor = "lightgreen"
            else:
                fillcolor = "lightgray"
            fontcolor = "black"
        label = f"{node.name}\\n(ID:{nid})\\n{'Aktif' if node.is_active else 'Tdk Aktif'}"
        lines.append(f'    "{nid}" [label="{label}", fillcolor="{fillcolor}", fontcolor="{fontcolor}"];')
        if node.left_child_id:
            lines.append(f'    "{nid}" -> "{node.left_child_id}";')
            queue.append(node.left_child_id)
        if node.right_child_id:
            lines.append(f'    "{nid}" -> "{node.right_child_id}";')
            queue.append(node.right_child_id)
    lines.append('}')
    return "\n".join(lines)

def get_member_tree_rich(root_id, members, search_id=None):
    descendants = get_descendants_rich(root_id, members)
    if not descendants:
        return ""
    lines = ['digraph G {', '    rankdir=TB;', '    node [shape=box, style=filled, fillcolor=lightblue, fontname="Arial"];']
    lines.append('    margin=0;')
    for nid in descendants:
        node = members[nid]
        if search_id == nid:
            fillcolor = "yellow"
            fontcolor = "black"
        else:
            fillcolor = "lightgreen"
            fontcolor = "black"
        label = f"{node.name}\\n(ID:{nid})\\nSaldo R: {node.balance_rich:,}"
        lines.append(f'    "{nid}" [label="{label}", fillcolor="{fillcolor}", fontcolor="{fontcolor}"];')
    for nid in descendants:
        node = members[nid]
        if node.sponsor_id and node.sponsor_id in descendants:
            lines.append(f'    "{node.sponsor_id}" -> "{nid}";')
    lines.append('}')
    return "\n".join(lines)

def get_tree_text(root_id, members, level=0):
    if root_id not in members:
        return []
    node = members[root_id]
    lines = []
    indent = "  " * level
    lines.append(f"{indent}├─ {node.name} (ID:{node.id}) [{'Aktif' if node.is_active else 'Tdk Aktif'}]")
    if node.left_child_id:
        lines.extend(get_tree_text(node.left_child_id, members, level+1))
    if node.right_child_id:
        lines.extend(get_tree_text(node.right_child_id, members, level+1))
    return lines

# ---------------------------- Sample dan Reset (Interaktif) ----------------------------
def create_sample_network():
    if len(st.session_state.members) > 1:
        st.warning("Reset aplikasi terlebih dahulu")
        return
    sample_data = [
        (1, "Member 1"), (1, "Member 2"),
        (2, "Member 3"), (2, "Member 4"),
        (3, "Member 5"), (3, "Member 6"),
        (4, "Member 7"), (4, "Member 8"),
        (5, "Member 9"), (5, "Member 10"),
    ]
    for sponsor_id, name in sample_data:
        register_member(sponsor_id, name)
    st.success("Sample 10 member berhasil dibuat")

def reset_app():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_interactive()
    st.rerun()

# ---------------------------- Ekspor/Impor State (Interaktif) ----------------------------
def export_state():
    state = {}
    members_dict = {}
    for mid, m in st.session_state.members.items():
        members_dict[mid] = {
            'id': m.id, 'name': m.name, 'sponsor_id': m.sponsor_id, 'parent_id': m.parent_id,
            'left_child_id': m.left_child_id, 'right_child_id': m.right_child_id,
            'is_active': m.is_active, 'balance_cuan': m.balance_cuan, 'balance_rich': m.balance_rich,
            'total_spent': m.total_spent, 'total_commission_received': m.total_commission_received
        }
    state['members'] = members_dict
    state['next_id'] = st.session_state.next_id
    state['total_cash_in'] = st.session_state.total_cash_in
    state['total_bonus_cuan'] = st.session_state.total_bonus_cuan
    state['total_bonus_rich'] = st.session_state.total_bonus_rich
    state['total_sponsor_bonus'] = st.session_state.total_sponsor_bonus
    state['transactions'] = st.session_state.transactions
    state['placement_queue'] = list(st.session_state.placement_queue)
    state['selected_sponsor_id'] = st.session_state.selected_sponsor_id
    state['reg_name'] = st.session_state.reg_name
    state['cuan_percent'] = st.session_state.cuan_percent
    state['rich_percent'] = st.session_state.rich_percent
    state['cuan_max_level'] = st.session_state.cuan_max_level
    state['rich_max_level'] = st.session_state.rich_max_level
    state['sponsor_bonus_percent'] = st.session_state.sponsor_bonus_percent
    state['min_spend_active'] = st.session_state.min_spend_active
    return state

def import_state(data):
    members = {}
    for mid, mdata in data['members'].items():
        m = Member(mdata['id'], mdata['name'], mdata['sponsor_id'], mdata['parent_id'], mdata['is_active'])
        m.left_child_id = mdata['left_child_id']
        m.right_child_id = mdata['right_child_id']
        m.balance_cuan = mdata['balance_cuan']
        m.balance_rich = mdata['balance_rich']
        m.total_spent = mdata['total_spent']
        m.total_commission_received = mdata['total_commission_received']
        members[int(mid)] = m
    st.session_state.members = members
    st.session_state.next_id = data['next_id']
    st.session_state.total_cash_in = data['total_cash_in']
    st.session_state.total_bonus_cuan = data['total_bonus_cuan']
    st.session_state.total_bonus_rich = data['total_bonus_rich']
    st.session_state.total_sponsor_bonus = data['total_sponsor_bonus']
    st.session_state.transactions = data['transactions']
    st.session_state.placement_queue = deque(data['placement_queue'])
    st.session_state.selected_sponsor_id = data['selected_sponsor_id']
    st.session_state.reg_name = data['reg_name']
    st.session_state.cuan_percent = data['cuan_percent']
    st.session_state.rich_percent = data['rich_percent']
    st.session_state.cuan_max_level = data['cuan_max_level']
    st.session_state.rich_max_level = data['rich_max_level']
    st.session_state.sponsor_bonus_percent = data['sponsor_bonus_percent']
    st.session_state.min_spend_active = data['min_spend_active']
    st.rerun()

# ---------------------------- Produk Card (Interaktif) ----------------------------
def product_card(product, member_id):
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        st.image("https://placehold.co/80x80?text=Produk", width=80)
    with col2:
        st.markdown(f"**{product['name']}**  \n{product['desc']}  \n💎 Harga: Rp{product['price']:,.0f}")
    with col3:
        if st.button(f"Beli", key=f"buy_{product['id']}_{member_id}"):
            if product['type'] == 'cuan':
                res = process_transaction_cuan(member_id, product['price'], apply_to_balance=True)
            else:
                res = process_transaction_rich(member_id, product['price'], apply_to_balance=True)
            if res:
                tx_detail = []
                for (mid, nama, desc, nominal) in (res['breakdown_cuan'] or res['breakdown_rich']):
                    tx_detail.append({"Member ID": mid, "Nama": nama, "Keterangan": desc, "Rp": nominal})
                tx = {
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'pembeli': res['buyer_name'], 'nominal': res['amount'],
                    'jenis': 'Auto Cuan' if product['type']=='cuan' else 'Auto Rich',
                    'total_komisi': res['total_bonus'], 'detail_komisi': tx_detail
                }
                st.session_state.transactions.append(tx)
                st.success(f"✅ Berhasil! Komisi: Rp{res['total_bonus']:,.0f}")
                st.dataframe(pd.DataFrame(tx_detail))
                st.balloons()

# ==================================================================================
# ============================ SIMULASI MASSAL (EFISIEN) ============================
# ==================================================================================

def build_tree_fast(n_members):
    """Bangun binary tree (placement) dan sponsor tree (sponsor = previous member)."""
    parent = [0] * (n_members + 1)
    left = [0] * (n_members + 1)
    right = [0] * (n_members + 1)
    sponsor = [0] * (n_members + 1)
    parent[1] = 0
    sponsor[1] = 0
    queue = deque([1])
    for new_id in range(2, n_members + 1):
        if not queue:
            break
        node_id = queue.popleft()
        if right[node_id] == 0:
            right[node_id] = new_id
            parent[new_id] = node_id
            if left[node_id] == 0:
                queue.append(node_id)
        elif left[node_id] == 0:
            left[node_id] = new_id
            parent[new_id] = node_id
        else:
            # node penuh, masukkan kedua anak ke antrian, lalu ulang dengan new_id yang sama
            queue.append(right[node_id])
            queue.append(left[node_id])
            queue.appendleft(node_id)  # kembalikan node penuh ke depan? Jangan, karena sudah penuh. Lebih baik: ambil node baru dari antrian lagi
            new_id -= 1  # ulang dengan new_id yang sama
            continue
        # sponsor: member baru disponsori oleh member sebelumnya (ID-1)
        sponsor[new_id] = new_id - 1 if new_id - 1 >= 1 else 1
        queue.append(new_id)
    # Pastikan semua member punya sponsor
    for i in range(2, n_members+1):
        if sponsor[i] == 0:
            sponsor[i] = 1
    return parent, left, right, sponsor

def precompute_ancestors(parent, max_level, n_members):
    ancestors = [[] for _ in range(n_members + 1)]
    for mid in range(1, n_members + 1):
        cur = parent[mid]
        level = 1
        while cur and level <= max_level:
            ancestors[mid].append((cur, level))
            cur = parent[cur]
            level += 1
    return ancestors

def run_mass_simulation(n_members, active_percent, avg_spend, margin,
                        cuan_percent, sponsor_bonus_percent, max_level, random_seed=42):
    random.seed(random_seed)
    start = time.time()
    parent, left, right, sponsor = build_tree_fast(n_members)
    ancestors = precompute_ancestors(parent, max_level, n_members)

    # Tentukan member aktif (belanja)
    n_active = int((n_members - 1) * active_percent / 100)
    all_members = list(range(2, n_members+1))
    if n_active > len(all_members):
        n_active = len(all_members)
    active_members = random.sample(all_members, n_active)
    is_active = [False] * (n_members + 1)
    for mid in active_members:
        is_active[mid] = True
    is_active[1] = True  # root aktif sebagai ancestor

    total_cash_in = n_active * avg_spend

    matrix_received = [0] * (n_members + 1)
    level_commission = [0] * (max_level + 1)

    for buyer in active_members:
        amount = avg_spend
        for anc_id, lvl in ancestors[buyer]:
            if is_active[anc_id]:
                perc = cuan_percent[lvl] if lvl < len(cuan_percent) else 0
                komisi = int(amount * perc)
                if komisi > 0:
                    matrix_received[anc_id] += komisi
                    level_commission[lvl] += komisi
            # jika ancestor tidak aktif -> komisi hangus (breakage)

    # Bonus sponsor berantai
    sponsor_bonus = [0] * (n_members + 1)
    for mid in range(1, n_members + 1):
        amount = matrix_received[mid]
        if amount == 0:
            continue
        current = mid
        chain = amount
        while True:
            sp = sponsor[current]
            if sp == 0:
                break
            bonus = int(chain * sponsor_bonus_percent)
            if bonus > 0:
                sponsor_bonus[sp] += bonus
                chain = bonus
                current = sp
            else:
                break

    total_matrix = sum(matrix_received)
    total_sponsor = sum(sponsor_bonus)
    total_bonus = total_matrix + total_sponsor
    laba_produk = total_cash_in * (margin / 100.0)
    profit = laba_produk - total_bonus

    max_komisi_per_transaksi = sum(cuan_percent[1:max_level+1])
    max_total_komisi = total_cash_in * max_komisi_per_transaksi
    breakage_matrix = max_total_komisi - total_matrix

    elapsed = time.time() - start
    return {
        'n_members': n_members, 'n_active': n_active, 'total_cash_in': total_cash_in,
        'total_matrix': total_matrix, 'total_sponsor': total_sponsor, 'total_bonus': total_bonus,
        'laba_produk': laba_produk, 'profit': profit, 'breakage_matrix': breakage_matrix,
        'level_commission': level_commission, 'elapsed': elapsed,
        'status': 'AMAN' if profit > 0 else ('RUGI' if profit < 0 else 'IMPAS')
    }

def run_batch_simulation(n_range, active_percent, avg_spend, margin, cuan_percent, sponsor_bonus_percent, max_level, random_seed=42):
    results = []
    for n in n_range:
        res = run_mass_simulation(n, active_percent, avg_spend, margin, cuan_percent, sponsor_bonus_percent, max_level, random_seed)
        results.append(res)
    return results

# ---------------------------- Main App ----------------------------
def main():
    st.set_page_config(page_title="K-BBPT Simulator", layout="wide")
    st.title("🛍️ K-BBPT Simulator + Analisis Massal")
    st.markdown("**Auto Cuan** (belanja ≥ Rp100.000) | **Auto Rich** (belanja bebas)")

    init_interactive()   # memastikan session state terisi (hanya sekali)

    with st.sidebar:
        st.header("🛠️ Manajemen")
        if st.button("🌳 Sample Jaringan 10 Member", use_container_width=True):
            create_sample_network()
        if st.button("🗑️ Reset Aplikasi", use_container_width=True):
            reset_app()
        st.markdown("---")
        st.header("💾 Backup & Restore")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Simpan JSON", use_container_width=True):
                state = export_state()
                json_str = json.dumps(state, indent=2, default=str)
                b64 = base64.b64encode(json_str.encode()).decode()
                href = f'<a href="data:application/json;base64,{b64}" download="kbppt_state.json">Download JSON</a>'
                st.markdown(href, unsafe_allow_html=True)
        with col2:
            uploaded = st.file_uploader("Muat JSON", type=["json"], key="upload", label_visibility="collapsed")
            if uploaded:
                try:
                    import_state(json.load(uploaded))
                    st.success("Data dimuat!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal: {e}")
        st.markdown("---")
        st.header("⚙️ Pengaturan Komisi (Global)")
        st.session_state.min_spend_active = st.number_input("Min belanja aktif", 0, 100000, 100000)
        st.session_state.sponsor_bonus_percent = st.slider("Bonus sponsor (%)", 0, 100, 20)/100.0
        st.write("Auto Cuan (% per level 1-8):")
        cols = st.columns(4)
        for i in range(1,9):
            default = [0,1,1,5,3,3,2,3,7][i]
            val = cols[(i-1)%4].number_input(f"L{i}", 0, 100, default, key=f"cuan_{i}")
            st.session_state.cuan_percent[i] = val/100.0
        st.write("Auto Rich (% per level 1-10):")
        cols2 = st.columns(5)
        default_rich = [0,5,5,4,4,2,1,1,1,1,1]
        for i in range(1,11):
            val = cols2[(i-1)%5].number_input(f"R{i}", 0, 100, default_rich[i], key=f"rich_{i}")
            st.session_state.rich_percent[i] = val/100.0

    tabs = st.tabs(["🏪 Belanja", "📊 Dashboard", "📝 Registrasi", "🌳 Visualisasi", "📈 Simulasi Massal"])

    with tabs[0]:  # Belanja
        st.header("🛒 Toko Produk")
        member_opts = {m.id: f"{m.name} (ID:{m.id})" for m in st.session_state.members.values()}
        if not member_opts:
            st.warning("Belum ada member")
            buyer_id = None
        else:
            buyer_id = st.selectbox("Member belanja", options=list(member_opts.keys()), format_func=lambda x: member_opts[x])
        filter_type = st.radio("Filter produk", ["Semua", "Auto Cuan", "Auto Rich"], horizontal=True)
        products = [
            {"id":1,"name":"Paket Bulanan","desc":"Auto Cuan","price":100000,"type":"cuan"},
            {"id":2,"name":"Paket Bulanan+","desc":"Auto Cuan","price":200000,"type":"cuan"},
            {"id":3,"name":"Suplemen","desc":"Auto Rich","price":50000,"type":"rich"},
            {"id":4,"name":"Vitamin C","desc":"Auto Rich","price":25000,"type":"rich"},
            {"id":5,"name":"Paket Herbal","desc":"Auto Rich","price":120000,"type":"rich"},
            {"id":6,"name":"Alat Kesehatan","desc":"Auto Rich","price":350000,"type":"rich"},
        ]
        filtered = [p for p in products if filter_type=="Semua" or (filter_type=="Auto Cuan" and p['type']=='cuan') or (filter_type=="Auto Rich" and p['type']=='rich')]
        if buyer_id:
            cols = st.columns(2)
            for i, prod in enumerate(filtered):
                with cols[i%2]:
                    product_card(prod, buyer_id)

    with tabs[1]:  # Dashboard
        st.header("Dashboard Interaktif")
        col1, col2, col3 = st.columns(3)
        total_member = len(st.session_state.members)
        active = sum(1 for m in st.session_state.members.values() if m.is_active)
        col1.metric("Total Member", total_member)
        col2.metric("Aktif", active)
        col3.metric("Cash In", f"Rp{st.session_state.total_cash_in:,.0f}")
        col4, col5, col6 = st.columns(3)
        col4.metric("Komisi Cuan", f"Rp{st.session_state.total_bonus_cuan:,.0f}")
        col5.metric("Bonus Sponsor", f"Rp{st.session_state.total_sponsor_bonus:,.0f}")
        col6.metric("Komisi Rich", f"Rp{st.session_state.total_bonus_rich:,.0f}")
        st.subheader("Riwayat Transaksi")
        if st.session_state.transactions:
            for tx in reversed(st.session_state.transactions[-20:]):
                with st.expander(f"{tx['timestamp']} - {tx['pembeli']} belanja Rp{tx['nominal']:,} - Total komisi Rp{tx['total_komisi']:,}"):
                    st.dataframe(pd.DataFrame(tx['detail_komisi']))
        st.subheader("Daftar Member")
        df = pd.DataFrame([{
            "ID": m.id, "Nama": m.name, "Sponsor": m.sponsor_id,
            "Parent Cuan": m.parent_id, "Status": "✅" if m.is_active else "❌",
            "Komisi Cuan": m.balance_cuan, "Komisi Rich": m.balance_rich
        } for m in st.session_state.members.values()])
        st.dataframe(df)

    with tabs[2]:  # Registrasi
        st.header("Registrasi Member Baru")
        name = st.text_input("Nama Lengkap", value=st.session_state.reg_name)
        st.session_state.reg_name = name
        sponsor_list = [(m.id, f"{m.name} (ID:{m.id})") for m in st.session_state.members.values()]
        idx = 0
        for i, (sid,_) in enumerate(sponsor_list):
            if sid == st.session_state.selected_sponsor_id:
                idx = i
                break
        sponsor = st.selectbox("Pilih Sponsor", options=sponsor_list, format_func=lambda x: x[1], index=idx)
        st.session_state.selected_sponsor_id = sponsor[0]
        if st.button("Daftar"):
            if not name.strip():
                st.error("Nama kosong")
            else:
                new, msg = register_member(sponsor[0], name.strip())
                if new:
                    st.success(msg)
                    st.session_state.reg_name = ""
                    st.session_state.selected_sponsor_id = 1
                    st.rerun()
                else:
                    st.error(msg)

    with tabs[3]:  # Visualisasi
        st.header("Visualisasi Jaringan")
        net_type = st.radio("Jenis jaringan", ["Auto Cuan (Binary)", "Auto Rich (Sponsor Tree)"])
        root = st.selectbox("Root", options=[m.id for m in st.session_state.members.values()], format_func=lambda x: st.session_state.members[x].name)
        search = st.text_input("Cari member")
        search_id = None
        if search:
            for m in st.session_state.members.values():
                if search.lower() == m.name.lower() or search == str(m.id):
                    search_id = m.id
                    break
            if not search_id:
                st.warning("Tidak ditemukan")
        if net_type == "Auto Cuan (Binary)":
            dot = get_member_tree_cuan(root, st.session_state.members, search_id)
        else:
            dot = get_member_tree_rich(root, st.session_state.members, search_id)
        if dot:
            st.graphviz_chart(dot)
        else:
            st.warning("Tidak bisa render graphviz")
        st.subheader("Text Tree")
        st.code("\n".join(get_tree_text(1, st.session_state.members)), language="text")

    with tabs[4]:  # Simulasi Massal
        st.header("📈 Simulasi Massal - Analisis Profit & Visualisasi Matriks")
        st.markdown("Atur asumsi di bawah, lalu jalankan simulasi. Grafik sensitivitas juga tersedia.")

        with st.expander("⚙️ Parameter Simulasi", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                n_members = st.number_input("Jumlah total member (termasuk root)", min_value=10, max_value=5000, value=500, step=50, key="mass_n")
                active_percent = st.slider("Persentase partisipasi belanja Auto Cuan (%)", 0, 100, 90, key="mass_active")
                avg_spend = st.number_input("Rata-rata nominal belanja (Rp)", min_value=100000, value=100000, step=50000, key="mass_spend")
            with col2:
                margin = st.number_input("Margin produk perusahaan (%)", min_value=0, max_value=100, value=5, step=1, key="mass_margin")
                random_seed = st.number_input("Random seed (reproduksi)", value=42, step=1, key="mass_seed")
                st.info("Parameter komisi mengikuti pengaturan di sidebar (persentase level matrix & bonus sponsor).")

        if st.button("🚀 Jalankan Simulasi untuk Satu Skenario", use_container_width=True):
            with st.spinner(f"Simulasi {n_members} member..."):
                cuan_percent = st.session_state.cuan_percent
                sponsor_bonus_percent = st.session_state.sponsor_bonus_percent
                max_level = st.session_state.cuan_max_level
                hasil = run_mass_simulation(n_members, active_percent, avg_spend, margin,
                                            cuan_percent, sponsor_bonus_percent, max_level, random_seed)
            st.success(f"Selesai dalam {hasil['elapsed']:.2f} detik")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Member", hasil['n_members'])
            c2.metric("Member Aktif", hasil['n_active'])
            c3.metric("Total Cash In", f"Rp{hasil['total_cash_in']:,.0f}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Komisi Matrix", f"Rp{hasil['total_matrix']:,.0f}")
            c2.metric("Total Bonus Sponsor", f"Rp{hasil['total_sponsor']:,.0f}")
            c3.metric("Total Bonus", f"Rp{hasil['total_bonus']:,.0f}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Laba Produk", f"Rp{hasil['laba_produk']:,.0f}")
            c2.metric("Profit Perusahaan", f"Rp{hasil['profit']:,.0f}", delta=f"{hasil['profit']/hasil['total_cash_in']*100:.1f}%")
            c3.metric("Status", hasil['status'])
            st.subheader("Distribusi Komisi Matrix per Level")
            df_level = pd.DataFrame({
                'Level': list(range(1, max_level+1)),
                'Persentase Komisi (%)': [cuan_percent[l]*100 for l in range(1, max_level+1)],
                'Total Komisi Diterima (Rp)': [hasil['level_commission'][l] for l in range(1, max_level+1)],
                '% dari Cash In': [hasil['level_commission'][l]/hasil['total_cash_in']*100 if hasil['total_cash_in']>0 else 0 for l in range(1, max_level+1)]
            })
            st.dataframe(df_level, use_container_width=True)
            fig, ax = plt.subplots()
            ax.bar(df_level['Level'], df_level['Total Komisi Diterima (Rp)'], color='skyblue')
            ax.set_xlabel('Level Matrix')
            ax.set_ylabel('Total Komisi (Rp)')
            ax.set_title('Komisi per Level')
            st.pyplot(fig)
            st.metric("Breakage Matrix (Bonus tidak tersalurkan)", f"Rp{hasil['breakage_matrix']:,.0f}")

        st.markdown("---")
        st.subheader("📊 Analisis Sensitivitas")
        with st.expander("Grafik Profit vs Jumlah Member", expanded=False):
            col1, col2 = st.columns([1,2])
            with col1:
                n_min = st.number_input("Min member", 10, 5000, 50, key="n_min")
                n_max = st.number_input("Max member", 10, 5000, 1000, key="n_max")
                n_step = st.number_input("Step", 10, 500, 50, key="n_step")
            if st.button("Generate Grafik Profit vs Jumlah Member", key="btn_member"):
                n_range = list(range(n_min, n_max+1, n_step))
                with st.spinner(f"Menjalankan {len(n_range)} simulasi..."):
                    cuan_percent = st.session_state.cuan_percent
                    sponsor_bonus_percent = st.session_state.sponsor_bonus_percent
                    max_level = st.session_state.cuan_max_level
                    results = run_batch_simulation(n_range, active_percent, avg_spend, margin,
                                                   cuan_percent, sponsor_bonus_percent, max_level, random_seed)
                profit_list = [r['profit'] for r in results]
                fig, ax = plt.subplots(figsize=(10,5))
                ax.plot(n_range, profit_list, marker='o', linestyle='-', color='green' if profit_list[-1]>0 else 'red')
                ax.axhline(y=0, color='gray', linestyle='--')
                ax.set_xlabel('Jumlah Member')
                ax.set_ylabel('Profit Perusahaan (Rp)')
                ax.set_title('Profit vs Jumlah Member')
                ax.grid(True)
                st.pyplot(fig)
                st.caption(f"Parameter tetap: partisipasi={active_percent}%, margin={margin}%, belanja=Rp{avg_spend:,.0f}")

        with st.expander("Grafik Profit vs Persentase Partisipasi", expanded=False):
            col1, col2 = st.columns([1,2])
            with col1:
                part_min = st.slider("Min partisipasi (%)", 0, 100, 0, key="part_min")
                part_max = st.slider("Max partisipasi (%)", 0, 100, 100, key="part_max")
                part_step = st.slider("Step (%)", 5, 20, 10, key="part_step")
            if st.button("Generate Grafik Profit vs Partisipasi", key="btn_part"):
                part_range = list(range(part_min, part_max+1, part_step))
                with st.spinner(f"Menjalankan {len(part_range)} simulasi..."):
                    cuan_percent = st.session_state.cuan_percent
                    sponsor_bonus_percent = st.session_state.sponsor_bonus_percent
                    max_level = st.session_state.cuan_max_level
                    profits = []
                    for p in part_range:
                        res = run_mass_simulation(n_members, p, avg_spend, margin,
                                                  cuan_percent, sponsor_bonus_percent, max_level, random_seed)
                        profits.append(res['profit'])
                fig, ax = plt.subplots(figsize=(10,5))
                ax.plot(part_range, profits, marker='s', linestyle='-', color='blue')
                ax.axhline(y=0, color='gray', linestyle='--')
                ax.set_xlabel('Persentase Partisipasi (%)')
                ax.set_ylabel('Profit Perusahaan (Rp)')
                ax.set_title(f'Profit vs Partisipasi (N={n_members})')
                ax.grid(True)
                st.pyplot(fig)
                st.caption(f"Parameter tetap: N={n_members}, margin={margin}%, belanja=Rp{avg_spend:,.0f}")

if __name__ == "__main__":
    main()
