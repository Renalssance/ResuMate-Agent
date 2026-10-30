declare module 'color4bg' {
  export type ColorBgOptions = {
    dom?: string
    colors?: string[]
    seed?: number
    loop?: boolean
    resize_mode?: string
    radius_inner?: number
    radius_outer?: number
  }

  export class AestheticFluidBg {
    constructor(options?: ColorBgOptions)
    update(option: 'scale', value: number): void
    destroy(): void
  }
}
