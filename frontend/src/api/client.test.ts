import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, REGIONS } from './client'

describe('REGIONS', () => {
  it('contains 5 Portuguese regions', () => {
    expect(REGIONS).toEqual(['Alentejo', 'Algarve', 'Centro', 'Lisboa', 'Norte'])
  })
})

describe('api client', () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function mockOkResponse(data: unknown) {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(data),
    })
  }

  function mockErrorResponse(status: number, body?: unknown) {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status,
      statusText: 'Not Found',
      json: body !== undefined ? () => Promise.resolve(body) : () => Promise.reject(new Error('no json')),
    })
  }

  describe('health', () => {
    it('calls GET /api/health', async () => {
      const data = { status: 'healthy', version: '1.0', uptime_seconds: 100, models_loaded: {} }
      mockOkResponse(data)

      const result = await api.health()

      expect(mockFetch).toHaveBeenCalledWith('/api/health', expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }))
      expect(result).toEqual(data)
    })
  })

  describe('predict', () => {
    it('calls POST /api/predict with body', async () => {
      const payload = {
        timestamp: '2024-01-01T00:00:00Z',
        region: 'Lisboa',
        temperature: 20,
        humidity: 50,
        wind_speed: 5,
        precipitation: 0,
        cloud_cover: 30,
        pressure: 1013,
      }
      const responseData = {
        timestamp: payload.timestamp,
        region: 'Lisboa',
        predicted_consumption_mw: 500,
        confidence_interval_lower: 450,
        confidence_interval_upper: 550,
        model_name: 'xgboost',
        confidence_level: 0.95,
        ci_method: 'quantile',
        ci_lower_clipped: false,
      }
      mockOkResponse(responseData)

      const result = await api.predict(payload)

      expect(mockFetch).toHaveBeenCalledWith('/api/predict', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      }))
      expect(result).toEqual(responseData)
    })
  })

  describe('predictBatch', () => {
    it('calls POST /api/predict/batch', async () => {
      const items = [{
        timestamp: '2024-01-01T00:00:00Z',
        region: 'Lisboa',
        temperature: 20,
        humidity: 50,
        wind_speed: 5,
        precipitation: 0,
        cloud_cover: 30,
        pressure: 1013,
      }]
      mockOkResponse({ predictions: [], total_predictions: 0 })

      await api.predictBatch(items)

      expect(mockFetch).toHaveBeenCalledWith('/api/predict/batch', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ items }),
      }))
    })
  })

  describe('predictExplain', () => {
    it('includes top_n query parameter', async () => {
      const data = {
        timestamp: '2024-01-01T00:00:00Z',
        region: 'Lisboa',
        temperature: 20,
        humidity: 50,
        wind_speed: 5,
        precipitation: 0,
        cloud_cover: 30,
        pressure: 1013,
      }
      mockOkResponse({ prediction: {}, top_features: [], explanation_method: 'shap', total_features: 0 })

      await api.predictExplain(data, 5)

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/predict/explain?top_n=5',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  describe('error handling', () => {
    it('throws with detail message from response body', async () => {
      mockErrorResponse(400, { detail: { message: 'Invalid input' } })

      await expect(api.health()).rejects.toThrow('Invalid input')
    })

    it('throws with HTTP status when body has no detail', async () => {
      mockErrorResponse(500, {})

      await expect(api.health()).rejects.toThrow('HTTP 500')
    })

    it('throws with statusText when JSON parsing fails', async () => {
      mockErrorResponse(404)

      await expect(api.health()).rejects.toThrow('Not Found')
    })
  })

  describe('regions', () => {
    it('calls GET /api/regions', async () => {
      mockOkResponse({ regions: ['Lisboa', 'Norte'] })

      const result = await api.regions()

      expect(mockFetch).toHaveBeenCalledWith('/api/regions', expect.any(Object))
      expect(result).toEqual({ regions: ['Lisboa', 'Norte'] })
    })
  })

  describe('modelInfo', () => {
    it('calls GET /api/model/info', async () => {
      mockOkResponse({ name: 'xgboost' })
      await api.modelInfo()
      expect(mockFetch).toHaveBeenCalledWith('/api/model/info', expect.any(Object))
    })
  })

  describe('driftCheck', () => {
    it('calls POST /api/model/drift/check with features', async () => {
      const features = { temperature: 25, humidity: 60 }
      mockOkResponse({ drifted: false })

      await api.driftCheck(features)

      expect(mockFetch).toHaveBeenCalledWith('/api/model/drift/check', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ features }),
      }))
    })
  })
})
