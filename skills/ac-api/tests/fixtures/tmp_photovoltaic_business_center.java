package base.business.energy.service;

import io.swagger.annotations.ApiModelProperty;
import java.math.BigDecimal;

@BusinessCenterDescriptor(name = "BusinessCenter4U3D", desc = "U3D")
public interface BusinessCenter4U3D {

    @BusinessDescriptor(desc = "光伏统计--U3D", name = "photovoltaicStatistics", returnDesc = "U3DPhotovoltaicStatisticsVO")
    U3DPhotovoltaicStatisticsVO photovoltaicStatistics(Integer projectId, Integer dateType);
}

class U3DPhotovoltaicStatisticsVO {

    /**
     * 发电量
     */
    private BigDecimal powerGeneration;

    /**
     * 同比发电量
     */
    private BigDecimal powerGenerationYoy;

    /**
     * 环比发电量
     */
    private BigDecimal powerGenerationMom;

    /**
     * 发电量同比百分比
     */
    private BigDecimal powerGenerationYoyRate;

    /**
     * 发电量环比百分比
     */
    private BigDecimal powerGenerationMomRate;

    @ApiModelProperty(value = "上网电量")
    private BigDecimal onGridEnergy;

    /**
     * 同比上网电量
     */
    private BigDecimal onGridEnergyYoy;

    /**
     * 环比上网电量
     */
    private BigDecimal onGridEnergyMom;

    /**
     * 同比上网电量百分比
     */
    private BigDecimal onGridEnergyYoyRate;

    /**
     * 环比上网电量百分比
     */
    private BigDecimal onGridEnergyMomRate;
}
