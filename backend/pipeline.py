"""Working baseline pipeline for the BAS Activity Intelligence project.

Uses Ultralytics YOLO pose for person detection/keypoints and a transparent
pose-based heuristic classifier. It keeps the AIVideoPipeline API expected by
main.py. It is a baseline, not a trained SIH26174 seven-class model.
"""
import os, math, json, logging, shutil
from collections import defaultdict, deque
from typing import Dict

from config import WEIGHTS_DIR, MODEL_CONFIG_PATH, POSE_WEIGHTS_NAME, POSE_WEIGHTS_PATH

log = logging.getLogger("bas.pipeline")

# Optional heavy dependencies: a missing package must be reported via the
# status endpoint, not crash the whole API on import.
IMPORT_ERRORS: Dict[str, str] = {}
try:
    import cv2
except Exception as e:  # pragma: no cover - depends on environment
    cv2 = None
    IMPORT_ERRORS["opencv"] = str(e)
try:
    from ultralytics import YOLO
except Exception as e:  # pragma: no cover - depends on environment
    YOLO = None
    IMPORT_ERRORS["ultralytics"] = str(e)

ENGINE_NAME = "Rule-based pose baseline"

# Frames per second actually run through the pose model. Video is decoded at full rate
# but only every Nth frame is inferred (vid_stride), which dominates processing time on CPU.
SAMPLE_FPS = 8.0
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
        self.load_error=None
        self._confidence_threshold=.60; self._unknown_sensitivity="Medium"
        self.config={}
        if os.path.exists(MODEL_CONFIG_PATH):
            try:
                with open(MODEL_CONFIG_PATH,encoding="utf-8") as f: self.config=json.load(f)
            except Exception as e:
                log.warning("Could not read %s: %s", MODEL_CONFIG_PATH, e)
        self.load_models()

    def get_model_status(self):
        return {
            "model_ready":self.model_ready,
            "detector_ready":self.detector_loaded,
            "classifier_ready":self.classifier_loaded,
            "baseline_mode":True,
            "engine":ENGINE_NAME,
            "classifier_type":"YOLO pose keypoints + rule-based activity baseline (no trained activity model)",
            "weights_directory":WEIGHTS_DIR,
            "files":{"pose_model":{"path":POSE_WEIGHTS_PATH,"exists":os.path.exists(POSE_WEIGHTS_PATH)}},
            "import_errors":IMPORT_ERRORS,
            "load_error":self.load_error,
            "activities":self.SUPPORTED_ACTIVITIES,
            "instructions":("Activity labels come from a rule-based baseline on pose keypoints. "
                            "A trained temporal model will be used automatically once its weights exist."),
        }

    def load_models(self):
        if IMPORT_ERRORS:
            self.load_error="Missing Python packages: "+", ".join(sorted(IMPORT_ERRORS))+". Run: pip install -r backend/requirements.txt"
            log.error(self.load_error); return
        if not os.path.exists(POSE_WEIGHTS_PATH):
            # Let ultralytics fetch the official weights once, then keep them in weights/.
            log.warning("Pose weights not found at %s; attempting one-time download of %s", POSE_WEIGHTS_PATH, POSE_WEIGHTS_NAME)
            try:
                YOLO(POSE_WEIGHTS_NAME)
                if os.path.exists(POSE_WEIGHTS_NAME) and not os.path.exists(POSE_WEIGHTS_PATH):
                    shutil.move(POSE_WEIGHTS_NAME, POSE_WEIGHTS_PATH)
            except Exception as e:
                self.load_error=f"Pose model {POSE_WEIGHTS_NAME} missing from {WEIGHTS_DIR} and download failed: {e}"
                log.error(self.load_error); return
        try:
            log.info("Loading pose model: %s", POSE_WEIGHTS_PATH)
            self.model=YOLO(POSE_WEIGHTS_PATH)
            self.model_loaded=self.detector_loaded=self.classifier_loaded=self.model_ready=True
            log.info("Pose model loaded; %s ready.", ENGINE_NAME)
        except Exception as e:
            self.load_error=f"Pose model failed to load: {e}"
            log.error(self.load_error)

    @property
    def confidence_threshold(self) -> float:
        """Events below this confidence (0-1) are sent to the Review Queue."""
        return self._confidence_threshold

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

    def process_video(self,path,progress_cb=None):
        """Run detection + tracking + activity classification over a video file.

        progress_cb(fraction) is called with 0..1 as frames are processed.
        """
        if not os.path.exists(path):
            return {"model_ready":False,"events":[],"metadata":{},"message":"Video file not found."}
        if not self.model_ready:
            return {"model_ready":False,"events":[],"metadata":{},"message":self.load_error or "Pose model is not loaded."}
        meta=self.get_video_metadata(path); fps=meta["fps"] or 30; every=max(1,round(fps/SAMPLE_FPS))
        total=max(1,meta["frame_count"])
        hist=defaultdict(lambda:deque(maxlen=15)); preds=defaultdict(list); detections=0; sampled=0
        try:
            stream=self.model.track(source=path,stream=True,persist=False,classes=[0],conf=.25,verbose=False,
                                    tracker="bytetrack.yaml",vid_stride=every)
            for idx,r in enumerate(stream):
                frame=idx*every; sampled+=1
                if progress_cb and idx%5==0: progress_cb(min(1.0,frame/total))
                if r.boxes is None or r.keypoints is None: continue
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
        except Exception as e:
            log.exception("Video processing failed for %s", path)
            return {"model_ready":True,"failed":True,"events":[],"metadata":meta,"message":f"Video processing failed: {e}"}

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
                "metadata":{**meta,"sample_every_frames":every,"sampled_frames":sampled,"detections":detections,
                             "people":len(preds),
                             "activity_engine":ENGINE_NAME},
                "message":(f"Processing complete: {len(preds)} people tracked, {len(events)} activity events ({ENGINE_NAME})."
                           if detections else
                           "Processing complete, but no people were detected in the video, so no activity events were produced.")}
