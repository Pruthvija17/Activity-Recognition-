"""Working baseline pipeline for the BAS Activity Intelligence project.

Uses Ultralytics YOLO pose for person detection/keypoints and a transparent
pose-based heuristic classifier. It keeps the AIVideoPipeline API expected by
main.py. It is a baseline, not a trained SIH26174 seven-class model.
"""
import os, math, json
from collections import defaultdict, deque
from typing import Any, Dict, List
import cv2

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

BASE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = os.path.join(BASE, "weights")
CONFIG = os.path.join(WEIGHTS, "model_config.json")
ACTIVITIES = ["Standing", "Sitting", "Walking", "Reaching",
              "Picking up an object", "Placing an object",
              "Handling experimental equipment"]


def hms(s):
    s = max(0, float(s)); h = int(s//3600); m = int((s%3600)//60); sec = int(s%60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def dist(a,b): return math.hypot(a[0]-b[0], a[1]-b[1])


def angle(a,b,c):
    try:
        v1=(a[0]-b[0],a[1]-b[1]); v2=(c[0]-b[0],c[1]-b[1])
        n1=math.hypot(*v1); n2=math.hypot(*v2)
        if n1*n2 < 1e-6: return 180
        x=max(-1,min(1,(v1[0]*v2[0]+v1[1]*v2[1])/(n1*n2)))
        return math.degrees(math.acos(x))
    except Exception: return 180


class AIVideoPipeline:
    SUPPORTED_ACTIVITIES = ACTIVITIES

    def __init__(self):
        self.model=None; self.model_loaded=False; self.model_ready=False
        self.detector_loaded=False; self.classifier_loaded=False
        self._confidence_threshold=.60; self._unknown_sensitivity="Medium"
        self.config={}
        if os.path.exists(CONFIG):
            try:
                with open(CONFIG,encoding="utf-8") as f: self.config=json.load(f)
            except Exception: pass
        self.load_models()

    def get_model_status(self):
        pose=os.path.join(WEIGHTS,"yolo11n-pose.pt")
        return {
            "model_ready":self.model_ready,
            "detector_ready":self.detector_loaded,
            "classifier_ready":self.classifier_loaded,
            "baseline_mode":True,
            "classifier_type":"YOLO pose + heuristic baseline",
            "weights_directory":WEIGHTS,
            "files":{"pose_model":{"path":pose,"exists":os.path.exists(pose)}},
            "activities":self.SUPPORTED_ACTIVITIES,
            "instructions":"This version uses a pose-based baseline because the supplied project has no trained activity_cnn.pt."
        }

    def load_models(self):
        if YOLO is None:
            print("[Pipeline] ultralytics is not installed."); return
        os.makedirs(WEIGHTS,exist_ok=True)
        local=os.path.join(WEIGHTS,"yolo11n-pose.pt")
        source=local if os.path.exists(local) else "yolo11n-pose.pt"
        try:
            print("[Pipeline] Loading:",source)
            self.model=YOLO(source)
            self.model_loaded=self.detector_loaded=self.classifier_loaded=self.model_ready=True
            print("[Pipeline] YOLO pose loaded; baseline activity engine ready.")
        except Exception as e:
            print("[Pipeline] Model load error:",e)

    def update_thresholds(self, confidence_threshold:int, unknown_sensitivity:str):
        self._confidence_threshold=max(.5,min(.95,float(confidence_threshold)/100))
        self._unknown_sensitivity=unknown_sensitivity or "Medium"

    def get_video_metadata(self,path):
        cap=cv2.VideoCapture(path)
        if not cap.isOpened(): raise RuntimeError("Could not open video")
        fps=float(cap.get(cv2.CAP_PROP_FPS) or 0); frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release(); duration=frames/fps if fps else 0
        return {"fps":round(fps,3),"frame_count":frames,"width":w,"height":h,
                "duration_seconds":round(duration,3),"duration":hms(duration),"filename":os.path.basename(path)}

    @staticmethod
    def p(k,i):
        if k is None or len(k)<=i: return None
        x,y=float(k[i][0]),float(k[i][1])
        return (x,y) if x>0 or y>0 else None

    def classify(self,k,bbox,hist):
        x1,y1,x2,y2=bbox; bw=max(1,x2-x1); bh=max(1,y2-y1)
        ls,rs=self.p(k,5),self.p(k,6); lw,rw=self.p(k,9),self.p(k,10)
        lh,rh=self.p(k,11),self.p(k,12); lk,rk=self.p(k,13),self.p(k,14)
        la,ra=self.p(k,15),self.p(k,16)
        shoulders=[p for p in (ls,rs) if p]; hips=[p for p in (lh,rh) if p]
        knees=[p for p in (lk,rk) if p]; wrists=[p for p in (lw,rw) if p]
        if not shoulders or not hips: return "Unknown",.3
        sh=(sum(p[0] for p in shoulders)/len(shoulders),sum(p[1] for p in shoulders)/len(shoulders))
        hip=(sum(p[0] for p in hips)/len(hips),sum(p[1] for p in hips)/len(hips))
        knee_angles=[]
        if lh and lk: knee_angles.append(angle(lh,lk,la or lk))
        if rh and rk: knee_angles.append(angle(rh,rk,ra or rk))
        ka=sum(knee_angles)/len(knee_angles) if knee_angles else 180
        center=((x1+x2)/2,(y1+y2)/2)
        movement=0
        if hist: movement=dist(center,hist[-1]["center"])/max(bw,bh)
        recent=movement
        if len(hist)>=5:
            cs=[z["center"] for z in list(hist)[-5:]]
            recent=sum(dist(cs[i],cs[i-1]) for i in range(1,len(cs)))/max(bw,bh)
        reach=False; low=False; front=False
        for w in wrists:
            dx=abs(w[0]-hip[0])/bw; above=(hip[1]-w[1])/bh
            reach |= dx>.28 and above>.10
            low |= w[1]>hip[1]+.08*bh
            front |= dx<.35 and -.25<(w[1]-hip[1])/bh<.35
        wrist_move=0
        if hist and hist[-1]["wrists"] and wrists:
            wrist_move=min(dist(a,b)/max(bw,bh) for a in wrists for b in hist[-1]["wrists"])
        if knees:
            ky=sum(p[1] for p in knees)/len(knees)
            if ka<145 and abs(ky-hip[1])/bh<.28: return "Sitting",.78
        if recent>.22: return "Walking",.76
        if reach: return "Reaching",.74
        if low and (wrist_move>.08 or recent>.15):
            return ("Placing an object" if hist and hist[-1].get("low") else "Picking up an object"),.65
        if front: return "Handling experimental equipment",.62
        if bh/bw>1.10 or abs(hip[1]-sh[1])/bh>.18: return "Standing",.72
        return "Unknown",.45

    def process_video(self,path):
        if not os.path.exists(path):
            return {"model_ready":False,"events":[],"metadata":{},"message":"Video file not found."}
        if not self.model_ready:
            return {"model_ready":False,"events":[],"metadata":{},"message":"YOLO pose model could not be loaded. Install ultralytics and allow its first-run model download."}
        meta=self.get_video_metadata(path); fps=meta["fps"] or 30; every=max(1,round(fps/10))
        hist=defaultdict(lambda:deque(maxlen=15)); preds=defaultdict(list); frame=0; detections=0
        try:
            stream=self.model.track(source=path,stream=True,persist=False,classes=[0],conf=.25,verbose=False,tracker="bytetrack.yaml")
            for r in stream:
                if frame%every: frame+=1; continue
                if r.boxes is None or r.keypoints is None: frame+=1; continue
                xy=r.boxes.xyxy.cpu().numpy(); kp=r.keypoints.xy.cpu().numpy()
                ids=r.boxes.id.cpu().numpy().astype(int).tolist() if r.boxes.id is not None else list(range(len(xy)))
                for i,b in enumerate(xy):
                    if i>=len(kp): continue
                    tid=int(ids[i]) if i<len(ids) else i
                    box=tuple(float(v) for v in b); k=kp[i]
                    activity,conf=self.classify(k,box,hist[tid]); t=frame/fps
                    wrists=[z for z in (self.p(k,9),self.p(k,10)) if z]
                    hist[tid].append({"center":((box[0]+box[2])/2,(box[1]+box[3])/2),"wrists":wrists,"low":any(w[1]>(box[1]+box[3])/2 for w in wrists)})
                    preds[tid].append({"frame":frame,"time":t,"activity":activity,"confidence":conf})
                    detections+=1
                frame+=1
        except Exception as e:
            return {"model_ready":True,"events":[],"metadata":meta,"message":f"Video processing failed: {e}"}

        events=[]
        for tid,ps in preds.items():
            if not ps: continue
            cur=ps[0]["activity"]; start=ps[0]["time"]; sf=ps[0]["frame"]; end=start; ef=sf; confs=[ps[0]["confidence"]]
            def flush():
                d=end-start
                if d<.35: return
                c=round(sum(confs)/len(confs),4)
                events.append({"person_id":f"Person {tid:02d}","activity":cur,"confidence":c,
                               "start":hms(start),"end":hms(end),"start_seconds":round(start,3),
                               "end_seconds":round(end,3),"duration":round(d,3),
                               "status":"Review" if cur=="Unknown" or c<.60 else "Confirmed",
                               "frame_start":sf,"frame_end":ef})
            for p in ps[1:]:
                if p["activity"]==cur:
                    confs.append(p["confidence"]); end=p["time"]; ef=p["frame"]
                else:
                    flush(); cur=p["activity"]; start=end=p["time"]; sf=ef=p["frame"]; confs=[p["confidence"]]
            flush()
        events.sort(key=lambda e:(e["start_seconds"],e["person_id"]))
        return {"model_ready":True,"events":events,
                "metadata":{**meta,"sample_every_frames":every,"detections":detections,
                             "activity_engine":"YOLO pose + heuristic baseline"},
                "message":f"Processing complete. Generated {len(events)} activity events using the pose-based baseline."}
