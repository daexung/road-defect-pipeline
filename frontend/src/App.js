import { useState, useEffect, useCallback } from "react";
import { MapContainer, TileLayer, Marker, useMap, Tooltip } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
import "./admin.css";

const createPinIcon = (color, symbol) =>
  L.divIcon({
    className: "",
    html: `
      <div style="width:32px;height:40px;display:flex;flex-direction:column;align-items:center;">
        <div style="
          width:32px;height:32px;
          background:${color};
          border-radius:50% 50% 50% 0;
          transform:rotate(-45deg);
          display:flex;align-items:center;justify-content:center;
          box-shadow:0 3px 10px rgba(0,0,0,0.3);
          border:2px solid white;
        ">
          <span style="transform:rotate(45deg);color:white;font-weight:900;font-size:15px;line-height:1;">${symbol}</span>
        </div>
        <div style="width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;border-top:8px solid ${color};margin-top:-1px;"></div>
      </div>`,
    iconSize: [32, 48],
    iconAnchor: [16, 48],
    popupAnchor: [0, -50],
  });

const POTHOLE_ICON = createPinIcon("#E53935", "!");
const SUSPECT_ICON = createPinIcon("#FB8C00", "?");

const isPothole = (cp_class) => Number(cp_class) === 3;
const isSuspect = (cp_class) => Number(cp_class) === 2;

const getDefectLabel = (event) => {
  if (event.cp_class_name) return event.cp_class_name;
  if (isPothole(event.cp_class)) return "포트홀";
  if (isSuspect(event.cp_class)) return "도로불량 의심 구역";
  return "도로불량";
};

const formatTime = (isoStr) => {
  if (!isoStr) return "시간 정보 없음";
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return "시간 형식 오류";
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(
    d.getDate()
  ).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
};

const getTodayString = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
};

// ─────────────────────────────────────────────
// 마커 + 툴팁
// ─────────────────────────────────────────────
function PinMarker({ event }) {
  const [address, setAddress] = useState("마커에 마우스를 올리면 주소를 조회합니다.");
  const [fetched, setFetched] = useState(false);
  const pothole = isPothole(event.cp_class);

  const handleMouseOver = () => {
    if (fetched) return;
    setAddress("주소 로딩 중...");
    fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${event.gps_lat}&lon=${event.gps_lng}&accept-language=ko`
    )
      .then((res) => res.json())
      .then((data) => {
        if (data && data.display_name) {
          const parts = data.display_name.split(", ");
          setAddress(parts.slice(0, 4).join(" "));
        } else {
          setAddress("주소 없음");
        }
        setFetched(true);
      })
      .catch(() => { setAddress("주소 조회 실패"); setFetched(true); });
  };

  return (
    <Marker
      position={[Number(event.gps_lat), Number(event.gps_lng)]}
      icon={pothole ? POTHOLE_ICON : SUSPECT_ICON}
      eventHandlers={{ mouseover: handleMouseOver }}
    >
      <Tooltip
        className={`custom-Tooltip ${pothole ? "Tooltip-red" : "Tooltip-orange"}`}
        direction="top" offset={[0, -60]} permanent={false} opacity={1} sticky={false}
      >
        <div className="Tooltip-header">
          <span className="Tooltip-dot" />
          <strong>{getDefectLabel(event)}</strong>
        </div>
        <div className="Tooltip-divider" />
        <div className="Tooltip-label">위치</div>
        <div className="Tooltip-time">{address}</div>
        <div className="Tooltip-divider" />
        <div className="Tooltip-label">최근 감지</div>
        <div className="Tooltip-time">{formatTime(event.event_timestamp)}</div>
      </Tooltip>
    </Marker>
  );
}

// ─────────────────────────────────────────────
// 지도 검색
// ─────────────────────────────────────────────
function MapSearch() {
  const map = useMap();
  const [query, setQuery] = useState("");

  const handleSearch = async () => {
    if (!query.trim()) return;
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=kr`
      );
      const data = await res.json();
      if (data.length > 0) map.setView([parseFloat(data[0].lat), parseFloat(data[0].lon)], 17);
      else alert("검색 결과가 없습니다.");
    } catch {
      alert("장소 검색 중 오류가 발생했습니다.");
    }
  };

  return (
    <div className="search-box">
      <span className="search-icon">🔍</span>
      <input
        type="text" placeholder="장소를 검색하세요" value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSearch()}
      />
      <button onClick={handleSearch}>검색</button>
    </div>
  );
}

// ─────────────────────────────────────────────
// 포트홀 목록 모달 (재사용)
// ─────────────────────────────────────────────
function ClusterListModal({ title, count, clusters, onClose }) {
  return (
    <div
      className="modal-overlay"
      style={{ zIndex: 9500 }}
      onClick={onClose}
    >
      <div
        className="modal-box"
        style={{
          maxWidth: "960px",
          width: "92%",
          maxHeight: "80vh",
          overflow: "auto",
          textAlign: "left",
          padding: "24px 28px",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div style={{ fontSize: "15px", fontWeight: 700, color: "#1a1a2e" }}>
            {title}
            <span className="admin-section-count" style={{ marginLeft: "8px" }}>{count}건</span>
          </div>
          <button
            className="admin-close-btn"
            style={{ background: "#1a1a2e" }}
            onClick={onClose}
          >
            ✕ 닫기
          </button>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>클러스터 ID</th>
                <th>유형</th>
                <th>위치 (위도/경도)</th>
                <th>주소</th>
                <th>감지 횟수</th>
                <th>최초 감지</th>
                <th>수리 여부</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((c) => (
                <tr key={c.cluster_id ?? c.event_id}>
                  <td className="admin-td-mono">{String(c.cluster_id ?? c.event_id).slice(0, 8)}…</td>
                  <td><span className="admin-tag red">{c.cp_class_name ?? "P"}</span></td>
                  <td className="admin-td-mono">
                    {Number(c.gps_lat).toFixed(4)}, {Number(c.gps_lng).toFixed(4)}
                  </td>
                  <td>{c.road_address ?? "-"}</td>
                  <td>{c.detection_count ?? "-"}회</td>
                  <td>{formatTime(c.first_event_timestamp ?? c.event_timestamp)}</td>
                  <td>
                    <span className={`admin-tag ${c.is_repaired ? "green" : "gray"}`}>
                      {c.is_repaired ? "수리완료" : "미수리"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// 관리자 대시보드
// ─────────────────────────────────────────────
const extractDong = (address) => {
  if (!address) return null;
  const match = address.match(/(\S+동)/);
  return match ? match[1] : null;
};

const groupByDong = (list) => {
  const map = {};
  list.forEach((item) => {
    const dong = extractDong(item.road_address);
    if (!dong) return;
    map[dong] = (map[dong] ?? 0) + 1;
  });
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
};

function AdminDashboard({ onClose, roadDefectEvents }) {
  const [selectedDate, setSelectedDate] = useState(getTodayString());
  const [reportData, setReportData]     = useState(null);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState(null);
  const [hnmDownloading, setHnmDownloading] = useState(false);
  const [dongTab, setDongTab]               = useState("daily");

  // 모달 상태: null | "new" | "unrepaired"
  const [clusterModal, setClusterModal] = useState(null);

  const baseUrl = process.env.REACT_APP_POTHOLE_API_BASE_URL;
  const apiKey  = process.env.REACT_APP_POTHOLE_API_KEY;

  const fetchReport = useCallback(async (date) => {
    setLoading(true);
    setError(null);
    setReportData(null);
    try {
      const res = await fetch(`${baseUrl}/api/report/${date}`, {
        headers: { "x-api-key": apiKey },
      });
      if (!res.ok) throw new Error(`데이터 없음 (${res.status})`);
      const data = await res.json();
      setReportData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [baseUrl, apiKey]);

  useEffect(() => { fetchReport(selectedDate); }, [selectedDate, fetchReport]);

  const handleHnmDownload = async () => {
    setHnmDownloading(true);
    try {
      const res = await fetch(`${baseUrl}/api/report/${selectedDate}/hnm-download`, {
        headers: { "x-api-key": apiKey },
      });
      if (!res.ok) throw new Error("다운로드 실패");
      const data = await res.json();
      const link = document.createElement("a");
      link.href = data.url;
      link.download = `hnm_candidates_${selectedDate}.csv`;
      link.click();
    } catch (err) {
      alert("HNM 로그 다운로드 실패: " + err.message);
    } finally {
      setHnmDownloading(false);
    }
  };

  const clusters = reportData?.pothole_clusters ?? {};
  const cpDist   = reportData?.cp_distribution ?? {};
  const runTime  = reportData?.run_inference_time ?? {};
  const speedUnc = reportData?.speed_uncertainty ?? {};
  const hnm      = reportData?.hnm_candidates ?? {};

  const RUN_LABELS = { first: "첫차", midday: "낮", last: "막차" };
  const CP_LABELS  = { "0": "정상 (N)", "1": "불확실-정상 (U_N)", "2": "불확실-포트홀 (U_P)", "3": "포트홀 (P)" };
  const CP_COLORS  = { "0": "#2E75B6", "1": "#696969", "2": "#F37338", "3": "#CF4500" };

  // 오늘 신규 P 클래스
  const pOnlyClusters = (clusters.today_new_clusters ?? []).filter((c) => Number(c.cp_class) === 3);
  const pOnlyCount    = pOnlyClusters.length;

  // 전체 미수리 P 클래스 (roadDefectEvents props에서)
  const totalUnrepairedP = (roadDefectEvents ?? []).filter(
    (e) => Number(e.cp_class) === 3 && !e.is_repaired
  );
  const unrepairedCount  = clusters.total_unrepaired_cluster_count ?? totalUnrepairedP.length;

  const dongRankingDaily  = groupByDong(pOnlyClusters);
  const dongRankingTotal  = groupByDong(totalUnrepairedP);
  const activeDongRanking = dongTab === "daily" ? dongRankingDaily : dongRankingTotal;
  const dongMaxCount      = activeDongRanking.length ? activeDongRanking[0][1] : 1;

  const minorCpEntries = Object.entries(cpDist).filter(([k]) => k !== "0");
  const minorTotal     = minorCpEntries.reduce((a, [, v]) => a + v, 0) || 1;
  const totalCp        = Object.values(cpDist).reduce((a, b) => a + b, 0) || 1;
  const nCount         = cpDist["0"] ?? 0;
  const nRatio         = ((nCount / totalCp) * 100).toFixed(1);

  const speedRatios = Object.values(speedUnc).map((v) => v.uncertain_ratio ?? 0).filter((v) => v > 0);
  const speedMin    = speedRatios.length ? Math.min(...speedRatios) : 0;
  const speedMax    = speedRatios.length ? Math.max(...speedRatios) : 1;
  const speedRange  = speedMax - speedMin || 0.01;

  const maxRunTime = Math.max(...Object.values(runTime).filter(Boolean), 1);

  return (
    <div className="admin-overlay">
      <div className="admin-panel">

        {/* 헤더 */}
        <div className="admin-header">
          <div className="admin-header-left">
            <span className="admin-badge">관리자</span>
            <h2 className="admin-title">일일 운행 분석 리포트</h2>
          </div>
          <div className="admin-header-right">
            <input
              type="date" className="admin-date-input"
              value={selectedDate} max={getTodayString()}
              onChange={(e) => setSelectedDate(e.target.value)}
            />
            <button className="admin-close-btn" onClick={onClose}>✕ 닫기</button>
          </div>
        </div>

        {loading && (
          <div className="admin-status">
            <div className="admin-spinner" />
            <span>데이터를 불러오는 중...</span>
          </div>
        )}
        {error && !loading && (
          <div className="admin-status error">
            ⚠️ {error} — 해당 날짜의 정보를 불러오는 데 실패했습니다.
          </div>
        )}

        {reportData && !loading && (
          <div className="admin-body">

            {/* ── 섹션 1: 현황 카드 ── */}
            <div className="admin-section-title">일일 영등포구 포트홀 현황</div>
            <div className="admin-cards">

              {/* 오늘 신규 포트홀 */}
              <div className="admin-card accent">
                <div className="admin-card-label">오늘 신규 포트홀 (P)</div>
                <div
                  className="admin-card-value"
                  onClick={() => pOnlyCount > 0 && setClusterModal("new")}
                  style={{
                    cursor: pOnlyCount > 0 ? "pointer" : "default",
                    textDecoration: pOnlyCount > 0 ? "underline" : "none",
                    textUnderlineOffset: "3px",
                  }}
                >
                  {pOnlyCount}
                  <span className="admin-card-unit">건</span>
                </div>
                {pOnlyCount > 0 && (
                  <div className="admin-card-hint">클릭하여 목록 보기 →</div>
                )}
                {clusters.change_rate_percent != null && (
                  <div className={`admin-card-badge ${clusters.change_rate_percent > 0 ? "up" : "down"}`}>
                    {clusters.change_rate_percent > 0 ? "▲" : "▼"} {Math.abs(clusters.change_rate_percent)}% 전일 대비
                  </div>
                )}
              </div>

              {/* 현재 미수리 포트홀 */}
              <div className="admin-card warning">
                <div className="admin-card-label">현재 포트홀 수 (미수리)</div>
                <div
                  className="admin-card-value"
                  onClick={() => totalUnrepairedP.length > 0 && setClusterModal("unrepaired")}
                  style={{
                    cursor: totalUnrepairedP.length > 0 ? "pointer" : "default",
                    textDecoration: totalUnrepairedP.length > 0 ? "underline" : "none",
                    textUnderlineOffset: "3px",
                  }}
                >
                  {unrepairedCount}
                  <span className="admin-card-unit">건</span>
                </div>
                {totalUnrepairedP.length > 0 && (
                  <div className="admin-card-hint">클릭하여 목록 보기 →</div>
                )}
              </div>

              {/* 수리 완료 */}
              <div className="admin-card success">
                <div className="admin-card-label">수리 완료</div>
                <div className="admin-card-value">
                  {clusters.total_repaired_cluster_count ?? "-"}
                  <span className="admin-card-unit">건</span>
                </div>
              </div>
            </div>

            {/* ── 섹션 2: 모델 성능 차트 ── */}
            <div className="admin-section-title">모델 성능 분석</div>
            <div className="admin-charts">

              <div className="admin-chart-card">
                <div className="admin-chart-title">결과 분포</div>
                <div className="admin-cp-normal-banner">
                  <span className="admin-cp-normal-label">정상 (N)</span>
                  <span className="admin-cp-normal-bar">
                    <span style={{ width: "100%", background: "#2E75B6", display: "block", height: "100%", borderRadius: "4px" }} />
                  </span>
                  <span className="admin-cp-normal-val">{nCount.toLocaleString()} ({nRatio}%)</span>
                </div>
                <div className="admin-cp-divider-label">이상 클래스 상세 비교</div>
                <div className="admin-bar-list">
                  {minorCpEntries.map(([k, v]) => (
                    <div key={k} className="admin-bar-row">
                      <div className="admin-bar-label">{CP_LABELS[k]}</div>
                      <div className="admin-bar-track">
                        <div className="admin-bar-fill" style={{ width: `${(v / minorTotal) * 100}%`, background: CP_COLORS[k] }} />
                      </div>
                      <div className="admin-bar-val">{v.toLocaleString()}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="admin-chart-card">
                <div className="admin-chart-title">회차별 평균 추론 시간</div>
                <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", flex: 1 }}>
                  <div className="admin-bar-list">
                    {Object.entries(runTime).map(([k, v]) => (
                      <div key={k} className="admin-bar-row">
                        <div className="admin-bar-label">{RUN_LABELS[k] ?? k}</div>
                        <div className="admin-bar-track">
                          <div className="admin-bar-fill" style={{ width: `${(v / maxRunTime) * 100}%`, background: "#2E75B6" }} />
                        </div>
                        <div className="admin-bar-val">{v}ms</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="admin-chart-card">
                <div className="admin-chart-title">
                  속도 구간별 불확실 예측 분포
                  <span className="admin-chart-note">※ 범위: {speedMin.toFixed(2)}% ~ {speedMax.toFixed(2)}%</span>
                </div>
                <div className="admin-bar-list">
                  {Object.entries(speedUnc).map(([k, v]) => {
                    const ratio = v.uncertain_ratio ?? 0;
                    const count = Math.round((v.total ?? 0) * (ratio / 100));
                    const barWidth = speedRange > 0 ? ((ratio - speedMin) / speedRange) * 80 + 20 : 50;
                    return (
                      <div key={k} className="admin-bar-row">
                        <div className="admin-bar-label">{k}</div>
                        <div className="admin-bar-track">
                          <div className="admin-bar-fill" style={{ width: `${barWidth}%`, background: "#F37338" }} />
                        </div>
                        <div className="admin-bar-val">
                          {count.toLocaleString()}건
                          <span style={{ fontSize: "10px", color: "#aaa", fontWeight: 400, marginLeft: "3px" }}>
                            ({ratio.toFixed(2)}%)
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="admin-chart-caption">고속 구간일수록 이미지 블러 → 불확실 예측 증가 가설 검증용</div>
              </div>

              <div className="admin-chart-card">
                <div className="admin-chart-title-row">
                  <span className="admin-chart-title">HNM 재학습 후보</span>
                  <button
                    className={`admin-download-btn ${hnmDownloading ? "loading" : ""}`}
                    onClick={handleHnmDownload}
                    disabled={hnmDownloading}
                  >
                    {hnmDownloading ? "준비 중..." : "CSV 다운로드"}
                  </button>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, padding: "12px 0" }}>
                  <div className="admin-hnm-label">전체 후보</div>
                  <div className="admin-hnm-value" style={{ fontSize: "36px", marginTop: "8px" }}>
                    {hnm.total ?? "-"}<span>건</span>
                  </div>
                  <div className="admin-hnm-desc" style={{ marginTop: "6px" }}>재학습 데이터 후보 총합</div>
                </div>
              </div>

            </div>

            {/* ── 섹션 3: 포트홀 밀집 구역 ── */}
            <div className="admin-section-title">포트홀 밀집 구역</div>
            <div className="admin-chart-card">
              <div className="admin-dong-tabs">
                <button className={`admin-dong-tab ${dongTab === "daily" ? "active" : ""}`} onClick={() => setDongTab("daily")}>
                  일별 (오늘 신규)
                </button>
                <button className={`admin-dong-tab ${dongTab === "total" ? "active" : ""}`} onClick={() => setDongTab("total")}>
                  전체 (누적 미수리)
                </button>
              </div>
              {activeDongRanking.length === 0 ? (
                <div className="admin-dong-empty">데이터 없음</div>
              ) : (
                <div className="admin-dong-list">
                  {activeDongRanking.map(([dong, count], idx) => (
                    <div key={dong} className="admin-dong-row">
                      <div className={`admin-dong-rank ${idx < 3 ? "top" : ""}`}>{idx + 1}</div>
                      <div className="admin-dong-name">{dong}</div>
                      <div className="admin-bar-track">
                        <div
                          className="admin-bar-fill"
                          style={{
                            width: `${(count / dongMaxCount) * 100}%`,
                            background: idx === 0 ? "#CF4500" : idx === 1 ? "#F37338" : idx === 2 ? "#FB8C00" : "#BDBDBD",
                          }}
                        />
                      </div>
                      <div className="admin-dong-count">{count}건</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        )}
      </div>

      {/* ── 오늘 신규 포트홀 모달 ── */}
      {clusterModal === "new" && (
        <ClusterListModal
          title="오늘 신규 포트홀 목록"
          count={pOnlyCount}
          clusters={pOnlyClusters}
          onClose={() => setClusterModal(null)}
        />
      )}

      {/* ── 미수리 포트홀 전체 모달 ── */}
      {clusterModal === "unrepaired" && (
        <ClusterListModal
          title="현재 미수리 포트홀 목록"
          count={totalUnrepairedP.length}
          clusters={totalUnrepairedP}
          onClose={() => setClusterModal(null)}
        />
      )}

    </div>
  );
}

// ─────────────────────────────────────────────
// 메인 앱
// ─────────────────────────────────────────────
export default function App() {
  const [checkedTypes, setCheckedTypes]             = useState({ pothole: false, suspect: false });
  const [roadDefectEvents, setRoadDefectEvents]     = useState([]);
  const [loading, setLoading]                       = useState(true);
  const [apiError, setApiError]                     = useState(null);
  const [modal, setModal]                           = useState(false);
  const [showPasswordModal, setShowPasswordModal]   = useState(false);
  const [showAdminDashboard, setShowAdminDashboard] = useState(false);
  const [passwordInput, setPasswordInput]           = useState("");
  const [passwordError, setPasswordError]           = useState(false);

  const ADMIN_PASSWORD = "admin1234";

  useEffect(() => {
    const fetchRoadDefectEvents = async () => {
      try {
        setLoading(true);
        setApiError(null);
        const baseUrl = process.env.REACT_APP_POTHOLE_API_BASE_URL;
        const apiKey  = process.env.REACT_APP_POTHOLE_API_KEY;
        if (!baseUrl) throw new Error("REACT_APP_POTHOLE_API_BASE_URL이 설정되지 않았습니다.");
        if (!apiKey)  throw new Error("REACT_APP_POTHOLE_API_KEY가 설정되지 않았습니다.");

        const response = await fetch(`${baseUrl}/api/road-defects/unrepaired`, {
          headers: { "x-api-key": apiKey },
        });
        if (!response.ok) throw new Error(`API 요청 실패: ${response.status}`);
        const data = await response.json();
        const list = Array.isArray(data)
          ? data
          : data.items || data.data || data.results ||
            data.road_defect_events || data.roadDefectEvents || data.defects || [];

        const cleaned = list
          .map((item, index) => ({
            event_id:        item.event_id ?? String(index),
            cluster_id:      item.cluster_id ?? item.event_id ?? String(index),
            event_timestamp: item.event_timestamp,
            first_event_timestamp: item.first_event_timestamp ?? item.event_timestamp,
            gps_lat:         Number(item.gps_lat),
            gps_lng:         Number(item.gps_lng),
            cp_class:        Number(item.cp_class),
            cp_class_name:   item.cp_class_name,
            is_repaired:     item.is_repaired,
            road_address:    item.road_address,
            detection_count: item.detection_count,
          }))
          .filter((item) =>
            Number.isFinite(item.gps_lat) &&
            Number.isFinite(item.gps_lng) &&
            Number.isFinite(item.cp_class)
          );
        setRoadDefectEvents(cleaned);
      } catch (err) {
        setApiError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchRoadDefectEvents();
  }, []);

  const FILTER_ITEMS = [
    { key: "pothole", label: "포트홀",       active: true  },
    { key: "suspect", label: "도로불량 의심", active: true  },
    { key: "drain",   label: "배수 불량",     active: false },
    { key: "ice",     label: "도로 결빙",     active: false },
    { key: "damage",  label: "노면 파손",     active: false },
  ];

  const handleCheck = (key, active) => {
    if (!active) { setModal(true); return; }
    setCheckedTypes((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleAdminClick = () => {
    setPasswordInput("");
    setPasswordError(false);
    setShowPasswordModal(true);
  };

  const handlePasswordSubmit = () => {
    if (passwordInput === ADMIN_PASSWORD) {
      setShowPasswordModal(false);
      setShowAdminDashboard(true);
    } else {
      setPasswordError(true);
    }
  };

  const visibleEvents = roadDefectEvents.filter((event) => {
    if (isPothole(event.cp_class) && checkedTypes.pothole) return true;
    if (isSuspect(event.cp_class) && checkedTypes.suspect) return true;
    return false;
  });

  return (
    <div className="app">

      {showAdminDashboard && (
        <AdminDashboard
          onClose={() => setShowAdminDashboard(false)}
          roadDefectEvents={roadDefectEvents}
        />
      )}

      <div className="logo-card">
        <span className="logo-text">도로안전 알리미</span>
      </div>

      <button className="admin-btn" onClick={handleAdminClick}>관리자 분석 리포트</button>

      <div className="filter-panel">
        <div className="filter-title">도로 불량 유형</div>
        {FILTER_ITEMS.map(({ key, label, active }) => (
          <label key={key} className={`filter-item ${!active ? "disabled" : ""}`}>
            <input
              type="checkbox"
              checked={!!checkedTypes[key]}
              onChange={() => handleCheck(key, active)}
            />
            <span className="checkmark" />
            <span className="filter-label">{label}</span>
            {!active && <span className="coming-soon">준비중</span>}
          </label>
        ))}
      </div>

      <div className="legend-card">
        <div className="legend-title">구분</div>
        <div className="legend-item"><span className="legend-dot red" /><span>도로불량</span></div>
        <div className="legend-item"><span className="legend-dot orange" /><span>도로불량 의심</span></div>
      </div>

      {loading  && <div className="status-card"><span>도로불량 데이터를 불러오는 중...</span></div>}
      {apiError && <div className="status-card error"><span>API 조회 실패: {apiError}</span></div>}

      <MapContainer center={[37.5365, 126.8990]} zoom={15} className="map" zoomControl={false}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; OpenStreetMap contributors'
        />
        <MapSearch />
        {visibleEvents.map((event) => (
          <PinMarker key={event.event_id} event={event} />
        ))}
      </MapContainer>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-icon">🚧</div>
            <div className="modal-title">현재 준비 중인 서비스입니다</div>
            <div className="modal-desc">빠른 시일 내에 제공될 예정입니다</div>
            <button className="modal-btn" onClick={() => setModal(false)}>확인</button>
          </div>
        </div>
      )}

      {showPasswordModal && (
        <div className="modal-overlay" onClick={() => setShowPasswordModal(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-icon">🔐</div>
            <div className="modal-title">관리자 인증</div>
            <div className="modal-desc">관리자 비밀번호를 입력하세요</div>
            <input
              type="password"
              className={`admin-password-input ${passwordError ? "error" : ""}`}
              placeholder="비밀번호"
              value={passwordInput}
              onChange={(e) => { setPasswordInput(e.target.value); setPasswordError(false); }}
              onKeyDown={(e) => e.key === "Enter" && handlePasswordSubmit()}
              autoFocus
            />
            {passwordError && (
              <div className="admin-password-error">비밀번호가 올바르지 않습니다</div>
            )}
            <div style={{ display: "flex", gap: "8px", marginTop: "16px" }}>
              <button className="modal-btn outline" onClick={() => setShowPasswordModal(false)}>취소</button>
              <button className="modal-btn" onClick={handlePasswordSubmit}>확인</button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}