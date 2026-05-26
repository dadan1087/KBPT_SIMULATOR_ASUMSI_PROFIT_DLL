import streamlit as st
from collections import deque
import pandas as pd
import numpy as np
from datetime import datetime
import json
import base64
import random

# ---------------------------- Data Model ----------------------------
class Member:
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

# ---------------------------- Algoritma Placement BFS (Prioritas Kanan) ----------------------------
def find_placement_cuan(members):
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

def build_tree(N, active_percent=100, seed=42):
    """Membangun pohon binary dengan N member (termasuk root Perusahaan).
       Mengembalikan dictionary members dan list member aktif (yang belanja)."""
    random.seed(seed)
    np.random.seed(seed)
    members = {1: Member(1, "Perusahaan", None, None, is_active=True)}
    next_id = 2
    for _ in range(1, N):
        parent_id, is_left = find_placement_cuan(members)
        new_id = next_id
        next_id += 1
        # Nama member default "Member X"
        name = f"Member {new_id-1}"
        # Sponsor untuk Auto Rich: pilih secara acak dari member yang sudah ada (bisa sendiri)
        # Agar tidak bias, pilih sponsor yang bukan dirinya sendiri dan bukan None.
        sponsor_candidates = [mid for mid in members if mid != new_id]
        sponsor_id = random.choice(sponsor_candidates) if sponsor_candidates else 1
        new_member = Member(new_id, name, sponsor_id, parent_id, is_active=False)
        members[new_id] = new_member
        parent = members[parent_id]
        if not is_left:
            parent.right_child_id = new_id
        else:
            parent.left_child_id = new_id
    # Tentukan status aktif berdasarkan persentase (kecuali root selalu aktif)
    member_ids = list(members.keys())
    # Root tetap aktif
    members[1].is_active = True
    # Untuk member lain, acak
    n_active = int((N - 1) * active_percent / 100)
    active_ids = random.sample([mid for mid in member_ids if mid != 1], n_active)
    for mid in active_ids:
        members[mid].is_active = True
    return members, active_ids

# ---------------------------- Fungsi Komisi Auto Cuan (massal) ----------------------------
def compute_cuan_commissions(members, active_ids, cuan_percent, max_level, sponsor_bonus_percent, min_spend=100000, avg_spend=100000):
    total_cash_in = 0
    total_matrix_commission = 0
    total_sponsor_bonus = 0
    # Reset balance
    for m in members.values():
        m.balance_cuan = 0
        m.total_commission_received = 0
    
    for mid in active_ids:
        amount = avg_spend  # asumsi semua belanja sama
        total_cash_in += amount
        # Naik ke ancestor (parent_id)
        ancestors = []
        cur = members[mid].parent_id
        level = 1
        while cur and level <= max_level:
            ancestors.append((cur, level))
            cur = members[cur].parent_id
            level += 1
        # Hitung komisi matrix
        for anc_id, lvl in ancestors:
            anc = members[anc_id]
            if anc.is_active:
                percent = cuan_percent[lvl] if lvl < len(cuan_percent) else 0
                komisi = int(amount * percent)
                if komisi > 0:
                    anc.balance_cuan += komisi
                    anc.total_commission_received += komisi
                    total_matrix_commission += komisi
    # Hitung bonus sponsor berantai
    # Bonus sponsor: 20% dari total komisi yang diterima downline langsung
    # Kita perlu iterasi sampai konvergen karena bonus berantai
    # Sederhana: urutkan dari member dengan ID besar ke kecil (asumsi ID lebih besar adalah downline)
    # Tapi lebih mudah: gunakan rekursif atau loop hingga tidak ada perubahan
    # Kita gunakan pendekatan: untuk setiap member, bonus sponsor = sum(20% * commission_received dari setiap downline langsung)
    # Lalu bonus tersebut juga dikenakan rantai.
    # Karena pohon sponsor tidak selalu terurut, kita lakukan iterasi berkali-kali
    # Untuk memudahkan, kita hitung bonus sponsor berdasarkan total komisi yang diterima masing-masing member
    # Lalu berikan bonus ke sponsor langsung, dan seterusnya.
    # Inisialisasi dictionary bonus tambahan
    additional_bonus = {mid: 0 for mid in members}
    # Kita lakukan beberapa iterasi karena rantai bisa panjang
    changed = True
    while changed:
        changed = False
        for mid in list(members.keys()):
            node = members[mid]
            if node.sponsor_id is None:
                continue
            sponsor = members[node.sponsor_id]
            # Bonus dari komisi yang diterima node (setelah termasuk bonus sebelumnya)
            total_received = node.balance_cuan + additional_bonus.get(mid, 0)
            bonus = int(total_received * sponsor_bonus_percent)
            if bonus > 0:
                key = node.sponsor_id
                if additional_bonus.get(key, 0) != additional_bonus.get(key, 0) + bonus:
                    additional_bonus[key] = additional_bonus.get(key, 0) + bonus
                    changed = True
    total_sponsor_bonus = sum(additional_bonus.values())
    # Tambahkan bonus ke balance cuan (untuk keperluan perhitungan lebih lanjut, tapi tidak diperlukan)
    total_bonus = total_matrix_commission + total_sponsor_bonus
    return total_cash_in, total_matrix_commission, total_sponsor_bonus, total_bonus

# ---------------------------- Fungsi Komisi Auto Rich (massal) ----------------------------
def compute_rich_commissions(members, active_ids, rich_percent, max_level, avg_spend=100000):
    total_cash_in = 0
    total_rich_commission = 0
    for m in members.values():
        m.balance_rich = 0
    for mid in active_ids:
        amount = avg_spend
        total_cash_in += amount
        # Naik melalui sponsor tree
        cur = members[mid].sponsor_id
        level = 1
        while cur and level <= max_level:
            anc = members[cur]
            percent = rich_percent[level] if level < len(rich_percent) else 0
            komisi = int(amount * percent)
            if komisi > 0:
                anc.balance_rich += komisi
                total_rich_commission += komisi
            cur = anc.sponsor_id
            level += 1
    return total_cash_in, total_rich_commission

# ---------------------------- Simulasi Massal ----------------------------
def run_mass_simulation(N, active_percent, avg_spend_cuan, avg_spend_rich, margin_percent,
                        cuan_percent, rich_percent, cuan_max_level, rich_max_level, sponsor_bonus_percent):
    # Bangun jaringan dengan N member
    members, active_ids = build_tree(N, active_percent, seed=42)
    # Hitung Auto Cuan
    cash_in_cuan, matrix_comm, sponsor_bonus, total_cuan_bonus = compute_cuan_commissions(
        members, active_ids, cuan_percent, cuan_max_level, sponsor_bonus_percent, 100000, avg_spend_cuan
    )
    # Hitung Auto Rich (pakai member aktif yang sama, atau bisa beda? Kita asumsikan sama)
    cash_in_rich, rich_comm = compute_rich_commissions(members, active_ids, rich_percent, rich_max_level, avg_spend_rich)
    total_cash_in = cash_in_cuan + cash_in_rich
    total_bonus = total_cuan_bonus + rich_comm
    laba_produk = total_cash_in * (margin_percent / 100)
    profit = laba_produk - total_bonus
    return {
        'N': N,
        'active_count': len(active_ids),
        'active_percent': active_percent,
        'cash_in_cuan': cash_in_cuan,
        'cash_in_rich': cash_in_rich,
        'total_cash_in': total_cash_in,
        'matrix_commission': matrix_comm,
        'sponsor_bonus': sponsor_bonus,
        'rich_commission': rich_comm,
        'total_bonus': total_bonus,
        'laba_produk': laba_produk,
        'profit': profit,
        'status': 'AMAN' if profit > 0 else ('RUGI' if profit < 0 else 'IMPAS')
    }

# ---------------------------- Streamlit UI (tambah tab simulasi massal) ----------------------------
# ... (kode sebelumnya untuk tab lain tetap ada, saya hanya akan menambahkan tab baru)

def main():
    st.set_page_config(page_title="K-BBPT Simulator", layout="wide")
    st.title("🛍️ K-BBPT Simulator - Analisis Bisnis")
    st.markdown("**Auto Cuan** (binary tree) | **Auto Rich** (sponsor tree)")

    # Inisialisasi session state jika belum ada (untuk mode interaktif)
    if 'members' not in st.session_state:
        reset_app()  # asumsi reset_app sudah didefinisikan seperti sebelumnya

    # Sidebar pengaturan umum (sama seperti sebelumnya)
    with st.sidebar:
        st.header("⚙️ Pengaturan Komisi")
        # ... (salin dari kode sebelumnya)
        # Saya singkat karena panjang, tapi intinya tetap ada
        st.session_state.cuan_percent = [0,0.01,0.01,0.05,0.03,0.03,0.02,0.03,0.07]
        st.session_state.rich_percent = [0,0.05,0.05,0.04,0.04,0.02,0.01,0.01,0.01,0.01,0.01]
        # ... (user bisa ubah via number_input)

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏪 Belanja", "📊 Dashboard", "📝 Registrasi", "🌳 Visualisasi", "📈 Simulasi Massal"])

    # ... (tab1-tab4 sama seperti kode sebelumnya, saya lewati karena hanya copy)

    with tab5:
        st.header("📊 Simulasi Massal dengan Parameter Asumsi")
        st.markdown("""
        Simulasi ini membangun jaringan dengan **N member** (binary tree untuk Auto Cuan, sponsor tree acak untuk Auto Rich).
        Kemudian menghitung total komisi yang terbayar dan profit perusahaan.
        """)
        col1, col2 = st.columns(2)
        with col1:
            N = st.number_input("Jumlah total member (termasuk Perusahaan)", min_value=2, max_value=5000, value=500, step=50)
            active_percent = st.slider("Persentase member aktif (belanja)", 0, 100, 90)
            avg_spend_cuan = st.number_input("Rata-rata belanja Auto Cuan (Rp)", min_value=100000, value=100000, step=50000)
            avg_spend_rich = st.number_input("Rata-rata belanja Auto Rich (Rp)", min_value=0, value=50000, step=10000)
        with col2:
            margin = st.number_input("Margin produk perusahaan (%)", min_value=0, max_value=100, value=5, step=1)
            # Parameter komisi bisa diambil dari session state (yang sudah diatur di sidebar)
            # Tampilkan parameter komisi yang digunakan
            st.write("**Auto Cuan % per level:**")
            cuan_str = ", ".join([f"{int(p*100)}" for p in st.session_state.cuan_percent[1:9]])
            st.info(f"L1-8: {cuan_str}%")
            st.write("**Auto Rich % per level:**")
            rich_str = ", ".join([f"{int(p*100)}" for p in st.session_state.rich_percent[1:11]])
            st.info(f"L1-10: {rich_str}%")
            st.write(f"**Bonus Sponsor:** {int(st.session_state.sponsor_bonus_percent*100)}% berantai")

        if st.button("🚀 Jalankan Simulasi", type="primary"):
            with st.spinner("Membangun jaringan dan menghitung komisi..."):
                result = run_mass_simulation(
                    N=N,
                    active_percent=active_percent,
                    avg_spend_cuan=avg_spend_cuan,
                    avg_spend_rich=avg_spend_rich,
                    margin_percent=margin,
                    cuan_percent=st.session_state.cuan_percent,
                    rich_percent=st.session_state.rich_percent,
                    cuan_max_level=8,
                    rich_max_level=10,
                    sponsor_bonus_percent=st.session_state.sponsor_bonus_percent
                )
            st.success("Simulasi selesai!")
            st.subheader("Hasil Simulasi")
            colA, colB, colC = st.columns(3)
            colA.metric("Total Member", result['N'])
            colA.metric("Member Aktif", f"{result['active_count']} ({result['active_percent']}%)")
            colB.metric("Total Cash In (Cuan)", f"Rp{result['cash_in_cuan']:,.0f}")
            colB.metric("Total Cash In (Rich)", f"Rp{result['cash_in_rich']:,.0f}")
            colB.metric("Total Cash In", f"Rp{result['total_cash_in']:,.0f}")
            colC.metric("Komisi Matrix Cuan", f"Rp{result['matrix_commission']:,.0f}")
            colC.metric("Bonus Sponsor", f"Rp{result['sponsor_bonus']:,.0f}")
            colC.metric("Komisi Auto Rich", f"Rp{result['rich_commission']:,.0f}")

            st.metric("Total Bonus Keluar", f"Rp{result['total_bonus']:,.0f}")
            st.metric("Laba dari Produk (margin)", f"Rp{result['laba_produk']:,.0f}")
            st.metric("Profit Bersih Perusahaan", f"Rp{result['profit']:,.0f}", delta_color="normal")
            if result['profit'] > 0:
                st.success(f"✅ Skema AMAN (profit positif: Rp{result['profit']:,.0f})")
            elif result['profit'] < 0:
                st.error(f"⚠️ Skema RUGI (profit negatif: Rp{result['profit']:,.0f}) – perlu evaluasi")
            else:
                st.info("⚖️ Skema IMPAS")

            # Tambahan analisis breakage sederhana
            # Hitung total potensi komisi jika semua level penuh dan semua aktif
            max_cuan_potential = result['cash_in_cuan'] * sum(st.session_state.cuan_percent[1:9])  # total % matrix 8 level
            max_rich_potential = result['cash_in_rich'] * sum(st.session_state.rich_percent[1:11])
            max_bonus_potential = result['matrix_commission'] * st.session_state.sponsor_bonus_percent  # perkiraan kasar
            total_potential = max_cuan_potential + max_rich_potential + max_bonus_potential
            breakage = total_potential - result['total_bonus']
            st.metric("Perkiraan Breakage", f"Rp{max(0, breakage):,.0f}", help="Selisih antara bonus maksimal teoritis dengan bonus terbayar")

if __name__ == "__main__":
    # Pastikan fungsi reset_app didefinisikan (salin dari kode sebelumnya)
    # Di sini saya hanya memberikan kerangka, Anda bisa gabungkan dengan kode sebelumnya.
    main()
