export interface AlertRecord {
  id: number;
  anomaly: {
    type: string;
    track_id?: number;
    count?: number;
    cluster_size?: number;
    cluster_bbox?: [number, number, number, number];
    cluster_area_px2?: number;
    density_per_kpx2?: number;
    duration?: number;
    avg_speed?: number;
    body_heights_per_sec?: number;
    avg_pair_speed?: number;
    distance?: number;
    track_ids?: number[];
    confidence?: number;
    owner_absent?: number;
    owner_track_id?: number;
    zone_id?: string;
    zone_name?: string;
    note?: string;
    class_name?: string;
    ppe_label?: string;
    bbox?: [number, number, number, number];
    position: [number, number] | null;
  };
  timestamp: number;
  iso: string;
  source?: string;
  snapshot_url?: string | null;
  acked?: 0 | 1;
  acked_at?: number | null;
  escalated?: boolean;
}
