export interface AlertRecord {
  id: number;
  anomaly: {
    type: string;
    track_id?: number;
    count?: number;
    duration?: number;
    avg_speed?: number;
    avg_pair_speed?: number;
    distance?: number;
    track_ids?: number[];
    confidence?: number;
    owner_absent?: number;
    zone_id?: string;
    zone_name?: string;
    note?: string;
    bbox?: [number, number, number, number];
    position: [number, number] | null;
  };
  timestamp: number;
  iso: string;
  source?: string;
  snapshot_url?: string | null;
}
