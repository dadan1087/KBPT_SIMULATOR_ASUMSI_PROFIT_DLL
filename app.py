import streamlit as st
from collections import deque
import pandas as pd
from datetime import datetime
import json
import base64
import random
import time

# ---------------------------- Data Model (Tetap digunakan untuk mode interaktif) ----------------------------
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

# ---------------------------- Algoritma Placement BFS (Prioritas Kanan) untuk mode interaktif ----------------------------
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
        return None, "Tidak ada slot kosong di binary tree."

    new_member = Member(new_id, name, sponsor_id, parent_id, is_active=True)
    members[new_id] = new_member
    parent = members[parent_id]
    if not is_left:
        parent.right_child_id = new_id
    else:
        parent.left_child_id = new_id

    side = "kanan" if not is_left else "kiri"
    info = (f"✅ Auto Cuan: anak {side} dari {parent.name} (ID:{parent.id})\n"
            f"✅ Auto Rich: sponsor langsung = {members[sponsor_id].name} (ID:{sponsor_id})")
    return new_member, info

# ---------------------------- Fungsi Komisi (mode interaktif) ----------------------------
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
        'buyer_name': member.name,
        'buyer_id': member_id,
        'amount': amount,
        'member_active': member.is_active,
        'ancestors_cuan': ancestors,
        'bonus_cuan': bonus_cuan,
        'bonus_rich': 0,
        'total_bonus': bonus_cuan + sponsor_bonus_total,
        'breakdown_cuan': breakdown_cuan,
        'breakdown_rich': []
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
        'buyer_name': member.name,
        'buyer_id': member_id,
        'amount': amount,
        'member_active': member.is_active,
        'bonus_cuan': 0,
        'bonus_rich': bonus_rich,
        'total_bonus': bonus_rich,
        'breakdown_cuan': [],
        'breakdown_rich': breakdown_rich
    }

# ---------------------------- Visualisasi (mode interaktif) ----------------------------
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

# ---------------------------- Export/Import State (mode interaktif) ----------------------------
def export_state():
    state = {}
    members_dict = {}
    for mid, m in st.session_state.members.items():
        members_dict[mid] = {
            'id': m.id,
            'name': m.name,
            'sponsor_id': m.sponsor_id,
            'parent_id': m.parent_id,
            'left_child_id': m.left_child_id,
            'right_child_id': m.right_child_id,
            'is_active': m.is_active,
            'balance_cuan': m.balance_cuan,
            'balance_rich': m.balance_rich,
            'total_spent': m.total_spent,
            'total_commission_received': m.total_commission_received
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
        m = Member(
            id=mdata['id'],
            name=mdata['name'],
            sponsor_id=mdata['sponsor_id'],
            parent_id=mdata['parent_id'],
            is_active=mdata['is_active']
        )
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

# ---------------------------- Sample dan Reset (mode interaktif) ----------------------------
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
    st.session_state.cuan_percent = [0, 0.01, 0.01, 0.05, 0.03, 0.03, 0.02, 0.03, 0.07]
    st.session_state.rich_percent = [0, 0.05, 0.05, 0.04, 0.04, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01]
    st.session_state.cuan_max_level = 8
    st.session_state.rich_max_level = 10
    st.session_state.sponsor_bonus_percent = 0.20
    st.session_state.min_spend_active = 100000
    st.rerun()

# ---------------------------- Produk Card (mode interaktif) ----------------------------
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
                if product['type'] == 'cuan':
                    for (mid, nama, desc, nominal) in res['breakdown_cuan']:
                        tx_detail.append({"Member ID": mid, "Nama": nama, "Keterangan": desc, "Rp": nominal})
                else:
                    for (mid, nama, desc, nominal) in res['breakdown_rich']:
                        tx_detail.append({"Member ID": mid, "Nama": nama, "Keterangan": desc, "Rp": nominal})
                tx = {
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'pembeli': res['buyer_name'],
                    'pembeli_id': res['buyer_id'],
                    'nominal': res['amount'],
                    'jenis': 'Auto Cuan' if product['type'] == 'cuan' else 'Auto Rich',
                    'total_komisi': res['total_bonus'],
                    'detail_komisi': tx_detail
                }
                st.session_state.transactions.append(tx)
                st.success(f"✅ Berhasil membeli {product['name']}!")
                st.info(f"Total Komisi: Rp{res['total_bonus']:,.0f}")
                if product['type'] == 'cuan':
                    st.write("**Jalur ancestor (dari bawah ke atas):**")
                    for aid, lvl in res['ancestors_cuan']:
                        st.write(f"Level {lvl}: {st.session_state.members[aid].name} (ID:{aid})")
                st.dataframe(pd.DataFrame(tx_detail), use_container_width=True)
                st.balloons()

# ==================================================================================
# ============================ SIMULASI MASSAL (EFISIEN) ============================
# ==================================================================================

def build_tree_fast(n_members):
    """
    Membangun binary tree dengan N member (root ID=1 sudah termasuk).
    Mengembalikan:
        parent: list of int, index=member_id, parent[1]=0 (tidak punya parent)
        left: list of int, left child id
        right: list of int, right child id
        sponsor: list of int, sponsor_id (untuk Auto Rich) - di sini diisi dengan random atau bisa 0.
            Untuk simulasi massal, sponsor tree tidak terlalu penting karena kita fokus ke Auto Cuan.
            Namun untuk bonus sponsor, kita perlu sponsor tree. Kita akan buat sponsor tree sederhana:
            setiap member baru disponsori oleh member dengan ID random atau member sebelumnya.
            Tapi karena kita hanya butuh perhitungan profit agregat, kita bisa asumsikan sponsor tree
            sama dengan placement tree? Tidak, karena dokumen menyatakan independen. Untuk menyederhanakan,
            kita asumsikan semua member disponsori oleh root (Perusahaan) -> maka bonus sponsor hanya
            mengalir ke root. Ini akan memberi estimasi profit terburuk (bonus besar). Atau kita buat
            sponsor tree sesuai urutan pendaftaran: member i disponsori oleh member i-1? Ini lebih realistis.
        Kita akan buat sponsor tree: member ke-2 disponsori root, member ke-3 disponsori member ke-2, dst.
        Namun untuk konsistensi, kita gunakan aturan: setiap member baru disponsori oleh member sebelumnya
        (kecuali root). Ini mirip dengan sample data.
    """
    parent = [0] * (n_members + 1)
    left = [0] * (n_members + 1)
    right = [0] * (n_members + 1)
    sponsor = [0] * (n_members + 1)   # sponsor untuk Auto Rich
    # root
    parent[1] = 0
    sponsor[1] = 0
    # queue untuk BFS placement
    queue = deque([1])
    next_id = 2
    # Urutan sponsor: member baru disponsori oleh member sebelumnya (ID-1) kecuali root
    # Ini untuk menyederhanakan, namun hasilnya masih cukup representatif.
    for new_id in range(2, n_members + 1):
        # Ambil node dari queue untuk placement
        if not queue:
            break
        node_id = queue.popleft()
        # Prioritas kanan
        if right[node_id] == 0:
            right[node_id] = new_id
            parent[new_id] = node_id
            # setelah diisi kanan, jika kiri masih kosong, node dikembalikan ke queue
            if left[node_id] == 0:
                queue.append(node_id)
        elif left[node_id] == 0:
            left[node_id] = new_id
            parent[new_id] = node_id
            # node menjadi penuh, tidak dikembalikan
        else:
            # seharusnya tidak terjadi karena node penuh tidak ada di queue
            # fallback: masukkan anak kanan dan kiri ke queue, lalu ulang
            queue.append(right[node_id])
            queue.append(left[node_id])
            # kita panggil rekursif sederhana dengan mengurangi new_id? Tidak efisien.
            # Untuk aman, kita bisa set new_id kembali dan loop lagi, tapi lebih mudah: kita ulangi proses dengan memasukkan node penuh ke queue?
            # Karena ini hanya simulasi, kita akan tempatkan di awal queue lagi dan ambil node berikutnya
            queue.appendleft(node_id)
            new_id -= 1
            continue
        # Sponsor: member baru disponsori oleh member sebelumnya (ID-1), jika ada; jika tidak, root
        if new_id - 1 >= 1:
            sponsor[new_id] = new_id - 1
        else:
            sponsor[new_id] = 1
        # Node baru memiliki dua slot kosong, tambahkan ke queue
        queue.append(new_id)
    # Pastikan semua member punya sponsor minimal root
    for i in range(2, n_members+1):
        if sponsor[i] == 0:
            sponsor[i] = 1
    return parent, left, right, sponsor

def precompute_ancestors(parent, max_level, n_members):
    """
    Untuk setiap member (1..n_members), precompute daftar ancestor hingga max_level.
    Mengembalikan list of list, ancestors[member_id] = list of (ancestor_id, level)
    """
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
                        cuan_percent, sponsor_bonus_percent, max_level,
                        random_seed=42):
    """
    Melakukan simulasi massal dengan N member.
    Mengembalikan dictionary hasil.
    """
    random.seed(random_seed)
    start_time = time.time()

    # 1. Bangun pohon
    parent, left, right, sponsor = build_tree_fast(n_members)
    # 2. Precompute ancestors untuk semua member
    ancestors = precompute_ancestors(parent, max_level, n_members)

    # 3. Tentukan member yang aktif (belanja)
    n_active = int(n_members * active_percent / 100)
    active_members = random.sample(range(2, n_members+1), n_active)  # exclude root? root tidak belanja sebagai member? root bisa dianggap tidak aktif belanja.
    # Root (ID=1) bisa saja tidak belanja. Kita exclude root dari aktivitas belanja.
    is_active = [False] * (n_members + 1)
    for mid in active_members:
        is_active[mid] = True
    # Root tetap aktif (sebagai ancestor) tapi tidak belanja
    is_active[1] = True

    total_cash_in = n_active * avg_spend

    # 4. Hitung komisi matrix
    # matrix_commission_received[mid] = total komisi matrix yang diterima member mid
    matrix_commission_received = [0] * (n_members + 1)

    for buyer_id in active_members:
        amount = avg_spend
        # naik ke ancestor
        for anc_id, level in ancestors[buyer_id]:
            if is_active[anc_id]:
                percent = cuan_percent[level] if level < len(cuan_percent) else 0
                komisi = int(amount * percent)
                if komisi > 0:
                    matrix_commission_received[anc_id] += komisi
            # jika ancestor tidak aktif, komisi hangus (tidak diterima siapa pun) -> breakage
            # tidak ada yang ditambahkan

    # 5. Hitung bonus sponsor berantai
    # Bonus sponsor: setiap member yang menerima komisi matrix, sponsornya mendapat sponsor_bonus_percent dari komisi tersebut,
    # lalu sponsor dari sponsor juga mendapat dari bonus tersebut, dst.
    # Kita iterasi semua member, untuk setiap komisi yang diterima, kita naikkan rantai sponsor.
    sponsor_bonus_received = [0] * (n_members + 1)
    for mid in range(1, n_members + 1):
        amount = matrix_commission_received[mid]
        if amount == 0:
            continue
        current = mid
        chain_amount = amount
        while True:
            sp_id = sponsor[current]
            if sp_id == 0:
                break
            bonus = int(chain_amount * sponsor_bonus_percent)
            if bonus > 0:
                sponsor_bonus_received[sp_id] += bonus
                chain_amount = bonus   # lanjutkan ke sponsor berikutnya dengan bonus yang diterima
                current = sp_id
            else:
                break

    total_matrix_bonus = sum(matrix_commission_received)
    total_sponsor_bonus = sum(sponsor_bonus_received)
    total_bonus = total_matrix_bonus + total_sponsor_bonus

    # 6. Hitung profit perusahaan
    laba_produk = total_cash_in * (margin / 100.0)
    profit = laba_produk - total_bonus

    # Hitung breakage teoritis: total komisi maksimal jika semua ancestor aktif dan semua level terisi penuh
    # Untuk setiap transaksi, komisi maksimal = amount * sum(cuan_percent[1..max_level])
    max_komisi_per_transaksi = sum(cuan_percent[1:max_level+1])
    max_total_komisi = total_cash_in * max_komisi_per_transaksi
    # Bonus sponsor maksimal? tidak dihitung sederhana, breakage kita hitung dari selisih antara maks komisi matrix dan real komisi matrix + bonus sponsor.
    # Namun lebih mudah: breakage matrix = max_total_komisi - total_matrix_bonus (karena bonus sponsor tidak memiliki batas atas teoritis)
    breakage_matrix = max_total_komisi - total_matrix_bonus

    elapsed = time.time() - start_time

    return {
        'n_members': n_members,
        'n_active': n_active,
        'total_cash_in': total_cash_in,
        'total_matrix_bonus': total_matrix_bonus,
        'total_sponsor_bonus': total_sponsor_bonus,
        'total_bonus': total_bonus,
        'laba_produk': laba_produk,
        'profit': profit,
        'breakage_matrix': breakage_matrix,
        'elapsed_time': elapsed,
        'status': 'AMAN' if profit > 0 else ('RUGI' if profit < 0 else 'IMPAS')
    }

# ---------------------------- Main App ----------------------------
def main():
    st.set_page_config(page_title="K-BBPT Simulator", layout="wide")
    st.title("🛍️ K-BBPT Simulator + Analisis Massal")
    st.markdown("**Auto Cuan** (belanja ≥ Rp100.000) | **Auto Rich** (belanja bebas)")

    if 'members' not in st.session_state:
        reset_app()

    # Sidebar umum
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

    # Tabs
    tab_belanja, tab_dashboard, tab_reg, tab_viz, tab_massal = st.tabs(
        ["🏪 Belanja", "📊 Dashboard", "📝 Registrasi", "🌳 Visualisasi", "📈 Simulasi Massal"]
    )

    with tab_belanja:
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

    with tab_dashboard:
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

    with tab_reg:
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

    with tab_viz:
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

    with tab_massal:
        st.header("📈 Simulasi Massal - Analisis Profit Perusahaan")
        st.markdown("""
        Gunakan simulator ini untuk mengetahui apakah skema komisi menguntungkan perusahaan 
        dalam skala besar. Masukkan asumsi jumlah member, persentase partisipasi belanja, 
        rata-rata nominal belanja, dan margin produk. Sistem akan membangun pohon binary 
        dengan N member (algoritma spillover round-robin) dan menghitung total bonus yang 
        keluar, serta profit perusahaan.
        """)
        with st.form("massal_form"):
            col1, col2 = st.columns(2)
            with col1:
                n_members = st.number_input("Jumlah total member (termasuk root)", min_value=10, max_value=10000, value=500, step=50)
                active_percent = st.slider("Persentase partisipasi belanja Auto Cuan (%)", 0, 100, 90)
                avg_spend = st.number_input("Rata-rata nominal belanja (Rp)", min_value=100000, value=100000, step=50000)
            with col2:
                margin = st.number_input("Margin produk perusahaan (%)", min_value=0, max_value=100, value=5, step=1)
                random_seed = st.number_input("Random seed (untuk reproduksi)", value=42, step=1)
            submitted = st.form_submit_button("🚀 Jalankan Simulasi", use_container_width=True)

        if submitted:
            with st.spinner(f"Sedang membangun pohon dengan {n_members} member dan melakukan simulasi..."):
                # Ambil parameter komisi dari session state (yang sudah diatur di sidebar)
                cuan_percent = st.session_state.cuan_percent.copy()
                sponsor_bonus_percent = st.session_state.sponsor_bonus_percent
                max_level = st.session_state.cuan_max_level
                # Jalankan simulasi
                hasil = run_mass_simulation(
                    n_members=n_members,
                    active_percent=active_percent,
                    avg_spend=avg_spend,
                    margin=margin,
                    cuan_percent=cuan_percent,
                    sponsor_bonus_percent=sponsor_bonus_percent,
                    max_level=max_level,
                    random_seed=random_seed
                )
            # Tampilkan hasil
            st.success(f"Simulasi selesai dalam {hasil['elapsed_time']:.2f} detik")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Member", hasil['n_members'])
            col2.metric("Member Aktif Belanja", hasil['n_active'])
            col3.metric("Total Cash In", f"Rp{hasil['total_cash_in']:,.0f}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Komisi Matrix", f"Rp{hasil['total_matrix_bonus']:,.0f}")
            col2.metric("Total Bonus Sponsor", f"Rp{hasil['total_sponsor_bonus']:,.0f}")
            col3.metric("Total Bonus Keseluruhan", f"Rp{hasil['total_bonus']:,.0f}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Laba dari Produk", f"Rp{hasil['laba_produk']:,.0f}")
            col2.metric("Profit Perusahaan", f"Rp{hasil['profit']:,.0f}", delta=f"{hasil['profit']/hasil['total_cash_in']*100:.1f}% dari cash in")
            col3.metric("Status", hasil['status'], delta="✅" if hasil['status']=='AMAN' else "⚠️" if hasil['status']=='RUGI' else "⚖️")

            st.subheader("Analisis Breakage")
            st.metric("Breakage Matrix (bonus tidak tersalurkan)", f"Rp{hasil['breakage_matrix']:,.0f}")
            st.caption("Breakage matrix adalah selisih antara komisi maksimal teoritis (jika semua level aktif dan penuh) dengan komisi matrix yang benar-benar terbayar.")

            # Tampilkan detail distribusi jika diperlukan (opsional)
            with st.expander("Lihat detail parameter simulasi"):
                st.json({
                    "Jumlah member": hasil['n_members'],
                    "Partisipasi": f"{active_percent}%",
                    "Rata-rata belanja": avg_spend,
                    "Margin produk": f"{margin}%",
                    "Random seed": random_seed,
                    "Persentase komisi per level": cuan_percent[1:max_level+1],
                    "Bonus sponsor": f"{sponsor_bonus_percent*100}%"
                })

if __name__ == "__main__":
    main()
