#pragma once
#include <stdint.h>
#include <math.h>
#include <float.h>
#include <string.h>

// Check IEEE-754 binary32 finiteness without the Xtensa unordered comparison
// emitted for isfinite(), which the Web simulator reports as unimplemented.
// memcpy preserves NaN/subnormal bits and avoids aliasing or type-punning.
inline bool isFiniteFloat32(float value) {
  static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24
    && FLT_MAX_EXP == 128, "This check requires IEEE-754 binary32 float");
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits & 0x7f800000u) != 0x7f800000u;
}

// All limits below are demonstrator settings, not validated medical thresholds.
struct Sample {
  float ax = 0, ay = 0, az = 9.80665f;
  float gx = 0, gy = 0, gz = 0; // radians per second
  int thumb = 1000, palm = 1000;
  bool contact = true;
  bool motionValid = true, thumbValid = true, palmValid = true, contactValid = true;
};

struct Pipeline {
  static constexpr float FORCE_LIMIT_PCT = 70;
  static constexpr uint32_t FORCE_HOLD_MS = 5000;
  static constexpr uint32_t CONTACT_REMINDER_MS = 20000;
  static constexpr uint32_t QUIET_MS = 10000;
  static constexpr uint32_t ABSENT_MS = 3000;
  static constexpr float ACCEL_ACTIVITY_MIN_M_S2 = 1.0f;
  static constexpr float GYRO_ALPHA = 0.2f, GYRO_ON = 0.05f, GYRO_OFF = 0.025f;
  static constexpr uint32_t GYRO_MIN_MS = 500, GYRO_REFRACTORY_MS = 400;
  static constexpr float GYRO_MIN_PATH = 0.05f;
  uint32_t total = 0, contactMs = 0, quietMs = 0, absentMs = 0;
  uint32_t thumbHighMs = 0, palmHighMs = 0, lastEvent = 0;
  uint32_t stamps[64] = {};
  uint8_t count = 0, head = 0;
  float previousX = 0, previousY = 0, previousZ = 0, filteredDelta = 0;
  float smoothGx = 0, smoothGy = 0, smoothGz = 0, gyroNorm = 0, previousGyroNorm = 0;
  float angularPath = 0, lastEpisodePath = 0;
  uint32_t episodeStart = 0, lastTrigger = 0, lastEpisodeDuration = 0, lastEpisodeStart = 0;
  uint32_t accelerationTotal = 0, accelerationLastEvent = 0;
  bool gyroInitialized = false, gyroArmed = false, episodeActive = false, hasTrigger = false;
  bool initialized = false, armed = true, movementEvent = false;
  bool pauseReminder = false, highForce = false, quietContact = false, absent = false;
  float thumbPct = NAN, palmPct = NAN;
  Sample last;

  void invalidateSegment() {
    initialized = gyroInitialized = episodeActive = false;
    filteredDelta = gyroNorm = previousGyroNorm = angularPath = 0;
    armed = true; gyroArmed = false;
    count = head = 0; // never count an old segment toward a fresh continuity window
  }

  void reset() { *this = Pipeline(); }
  uint32_t windowCount(uint32_t now) const {
    uint32_t result = 0;
    for (uint8_t i = 0; i < count; ++i)
      if (now - stamps[i] < 10000) ++result;
    return result;
  }
  void update(Sample sample, uint32_t now, uint32_t dt = 50) {
    // Never bridge a long acquisition gap as continuous evidence.
    if (dt > 200) {
      contactMs = quietMs = thumbHighMs = palmHighMs = absentMs = 0;
      invalidateSegment();
      dt = 0;
    }
    sample.motionValid = sample.motionValid && isFiniteFloat32(sample.ax) && isFiniteFloat32(sample.ay)
      && isFiniteFloat32(sample.az) && fabsf(sample.ax) < 19.5f
      && fabsf(sample.ay) < 19.5f && fabsf(sample.az) < 19.5f;
    sample.motionValid = sample.motionValid && isFiniteFloat32(sample.gx) && isFiniteFloat32(sample.gy)
      && isFiniteFloat32(sample.gz) && fabsf(sample.gx) < 4.35f
      && fabsf(sample.gy) < 4.35f && fabsf(sample.gz) < 4.35f;
    sample.thumbValid = sample.thumbValid && sample.thumb >= 0 && sample.thumb <= 4095;
    sample.palmValid = sample.palmValid && sample.palm >= 0 && sample.palm <= 4095;
    last = sample;
    thumbPct = sample.thumbValid ? sample.thumb * 100.0f / 4095.0f : NAN;
    palmPct = sample.palmValid ? sample.palm * 100.0f / 4095.0f : NAN;
    movementEvent = false;

    if (sample.motionValid) {
      if (initialized) {
        const float dx = sample.ax - previousX, dy = sample.ay - previousY, dz = sample.az - previousZ;
        filteredDelta = 0.5f * filteredDelta + 0.5f * sqrtf(dx * dx + dy * dy + dz * dz);
        if (filteredDelta < 0.35f) armed = true;
        // Secondary acceleration indicator retained; it is not added to the gyro count.
        if (armed && filteredDelta >= ACCEL_ACTIVITY_MIN_M_S2 && (accelerationTotal == 0 || now - accelerationLastEvent >= 250)) {
          armed = false;
          accelerationLastEvent = now;
          ++accelerationTotal;
        }
      }
      previousX = sample.ax; previousY = sample.ay; previousZ = sample.az;
      initialized = true;

      // Port of the offline gyro V2 rule. Native samples target 20 Hz; no
      // future interpolation is used on the ESP32. Confirmation is at release.
      if (!gyroInitialized) {
        smoothGx = sample.gx; smoothGy = sample.gy; smoothGz = sample.gz;
        gyroNorm = sqrtf(smoothGx*smoothGx + smoothGy*smoothGy + smoothGz*smoothGz);
        gyroArmed = gyroNorm < GYRO_OFF; // do not invent a start on reconnect
        gyroInitialized = true;
      } else {
        smoothGx += GYRO_ALPHA * (sample.gx - smoothGx);
        smoothGy += GYRO_ALPHA * (sample.gy - smoothGy);
        smoothGz += GYRO_ALPHA * (sample.gz - smoothGz);
        gyroNorm = sqrtf(smoothGx*smoothGx + smoothGy*smoothGy + smoothGz*smoothGz);
        if (episodeActive) angularPath += previousGyroNorm * (dt / 1000.0f);
        if (gyroNorm < GYRO_OFF) {
          gyroArmed = true;
          if (episodeActive) {
            const uint32_t duration = now - episodeStart;
            if (duration >= GYRO_MIN_MS && angularPath + 1e-6f >= GYRO_MIN_PATH) {
              movementEvent = true; ++total; lastEvent = now;
              lastEpisodeStart = episodeStart; lastEpisodeDuration = duration;
              lastEpisodePath = angularPath;
              stamps[head] = now; head = (head + 1) % 64;
              if (count < 64) ++count;
            }
            episodeActive = false;
          }
        }
        if (!episodeActive && gyroArmed && gyroNorm >= GYRO_ON
            && (!hasTrigger || now - lastTrigger >= GYRO_REFRACTORY_MS)) {
          episodeActive = true; episodeStart = now; angularPath = 0;
          gyroArmed = false; hasTrigger = true; lastTrigger = now;
        }
      }
      previousGyroNorm = gyroNorm;
    } else {
      invalidateSegment();
    }

    if (sample.contactValid && sample.contact) {
      absentMs = 0;
      contactMs += dt;
      // Acceleration activity also interrupts quiet time, including a sustained
      // signal that keeps the secondary event detector disarmed. It never adds
      // an episode to the gyro counter.
      if (sample.motionValid) quietMs = (episodeActive || movementEvent || gyroNorm >= GYRO_OFF
        || filteredDelta >= ACCEL_ACTIVITY_MIN_M_S2) ? 0 : quietMs + dt;
      else quietMs = 0;
    } else {
      quietMs = 0;
      if (sample.contactValid) {
        absentMs += dt;
        if (absentMs >= ABSENT_MS) contactMs = 0;
      } else { absentMs = contactMs = 0; }
    }
    // The absence of contact suppresses usage reminders, not measurement acquisition.
    const bool contactOk = sample.contactValid && sample.contact;
    thumbHighMs = contactOk && sample.thumbValid && thumbPct >= FORCE_LIMIT_PCT ? thumbHighMs + dt : 0;
    palmHighMs = contactOk && sample.palmValid && palmPct >= FORCE_LIMIT_PCT ? palmHighMs + dt : 0;
    highForce = thumbHighMs >= FORCE_HOLD_MS || palmHighMs >= FORCE_HOLD_MS;
    pauseReminder = contactOk && sample.motionValid && contactMs >= CONTACT_REMINDER_MS
      && windowCount(now) >= 10;
    quietContact = contactOk && sample.motionValid && quietMs >= QUIET_MS;
    absent = sample.contactValid && !sample.contact && absentMs >= ABSENT_MS;
  }
};

inline Sample presetSample(uint8_t scenario, uint32_t elapsed) {
  Sample s;
  if (scenario == 1) { // normal: 8 seconds of contact, 6 seconds without contact
    s.contact = elapsed % 14000 < 8000;
    s.ax = s.contact && elapsed % 1500 < 150 ? 4.0f : 0;
    s.gz = s.contact && elapsed % 1500 >= 100 && elapsed % 1500 < 450 ? 0.2f : 0;
    s.thumb = s.contact ? 1000 : 0; s.palm = s.contact ? 1200 : 0;
  } else if (scenario == 2) { // repetitive synthetic motion
    s.ax = elapsed % 500 < 100 ? 5.0f : 0;
    s.gz = elapsed % 850 >= 50 && elapsed % 850 < 350 ? 0.25f : 0;
  } else if (scenario == 3) { // sustained simulated pressure
    s.thumb = 3500; s.palm = 3300;
    s.ax = elapsed % 1500 < 150 ? 4.0f : 0;
    s.gz = elapsed % 1500 >= 100 && elapsed % 1500 < 450 ? 0.2f : 0;
  } else if (scenario == 4) { // immobile, alternating contact after 12 s
    s.contact = elapsed % 24000 < 12000;
    s.thumb = s.contact ? 1000 : 0; s.palm = s.contact ? 1000 : 0;
  } else if (scenario == 5) { // explicit injected invalidity, not an analog wire-break detector
    s.ax = NAN; s.gx = NAN; s.thumb = 5000; s.palm = -1;
  } else if (scenario == 6) { // network transport interrupted separately
    s.ax = elapsed % 1500 < 150 ? 4.0f : 0;
    s.gz = elapsed % 1500 >= 100 && elapsed % 1500 < 450 ? 0.2f : 0;
  }
  return s;
}

inline bool pipelineSelfTest() {
  Pipeline p;
  for (uint32_t t = 0; t < 30000; t += 50) p.update(presetSample(1, t), t);
  if (p.pauseReminder || p.highForce) return false;
  p.reset();
  for (uint32_t t = 0; t < 22000; t += 50) p.update(presetSample(2, t), t);
  if (!p.pauseReminder || p.total < 20) return false;
  p.reset();
  for (uint32_t t = 0; t < 6000; t += 50) p.update(presetSample(3, t), t);
  if (!p.highForce) return false;
  p.update(presetSample(5, 0), 6050);
  if (p.highForce || p.pauseReminder || p.last.motionValid || p.last.thumbValid || p.last.palmValid
      || !isnan(p.thumbPct) || !isnan(p.palmPct)) return false;
  p.reset();
  for (uint32_t t = 0; t < 11000; t += 50) p.update(presetSample(4, t), t);
  if (!p.quietContact || p.absent) return false;
  for (uint32_t t = 11000; t < 16000; t += 50) p.update(presetSample(4, t), t);
  if (p.quietContact || !p.absent || p.contactMs != 0) return false;
  // Zero force is a valid measurement; a constant sensor is not proof of failure.
  Sample zero; zero.thumb = zero.palm = 0;
  p.update(zero, 16050);
  if (!p.last.thumbValid || p.thumbPct != 0) return false;
  p.reset();
  for (uint32_t t = 0; t < 4900; t += 50) p.update(presetSample(3, t), t);
  p.update(presetSample(3, 6000), 6000, 1100);
  if (p.highForce) return false;
  // A new segment must not inherit the EMA value from before an acquisition gap.
  p.reset();
  Sample motion;
  motion.ax = 0; p.update(motion, 50, 50);
  motion.ax = 1.6f; p.update(motion, 100, 50);
  motion.ax = 0; p.update(motion, 1100, 1000);
  motion.ax = 1.4f; p.update(motion, 1150, 50);
  if (p.accelerationTotal != 0 || fabsf(p.filteredDelta - 0.7f) > 0.001f) return false;
  // A pre-gap event must not leave detection disarmed for the new segment.
  p.reset();
  motion.ax = 0; p.update(motion, 50, 50);
  motion.ax = 4; p.update(motion, 100, 50);
  motion.ax = 0; p.update(motion, 1100, 1000);
  motion.ax = 3; p.update(motion, 1150, 50);
  if (p.accelerationTotal != 2 || p.total != 0) return false;
  // Rotation-only input must count, and must not count until release.
  p.reset(); Sample rotation;
  p.update(rotation, 0, 0);
  rotation.gz = 0.2f;
  for (uint32_t t = 50; t <= 1000; t += 50) p.update(rotation, t);
  if (p.total != 0 || !p.episodeActive) return false;
  rotation.gz = 0;
  for (uint32_t t = 1050; t <= 1800; t += 50) p.update(rotation, t);
  if (p.total != 1 || p.accelerationTotal != 0 || p.lastEpisodeDuration < 500) return false;
  // An interrupted rotation is incomplete and must never be confirmed.
  p.reset(); p.update(rotation, 0, 0); rotation.gz = 0.2f;
  for (uint32_t t = 50; t <= 1000; t += 50) p.update(rotation, t);
  p.update(rotation, 1600, 600); rotation.gz = 0;
  for (uint32_t t = 1650; t <= 2500; t += 50) p.update(rotation, t);
  if (p.total != 0) return false;
  return true;
}
